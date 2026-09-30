"""AIService — functional chat facade for the UI layer.

Architecture:
    AIChatPanelWidget → CommandBus(ai.chat) → AIPlugin → AIService → AIProvider

Responsibilities:
    - Expose the locked chat API: chat(), stream(), history, state
    - Publish ai.* events on EventBus so future voice / gesture / panel
      subscribers can react without touching this layer
    - Never expose provider internals to widgets or plugins
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

from aether.ai.context import ContextBuilder, ContextEngine, MemoryContext
from aether.ai.intent import (
    ACT_MEMORY_SEARCH,
    ACT_MEMORY_WRITE,
    ACT_ASK_CLARIFICATION,
    IntentReasoner,
)
from aether.ai.models import AIResult, AIState, ChatMessage, ChatRole
from aether.ai.provider import AIProvider, EchoProvider, ProviderError
from aether.ai.stream import StreamEvent
from aether.ai.tools import ToolExecutor, ToolRegistry, ToolResult
from aether.core.event_bus_v2 import Event, EventBus
from aether.core.event_type import EventType

logger = logging.getLogger("Aether.AIService")

EVENT_SOURCE = "ai.service"

DEFAULT_MAX_HISTORY = 20
DEFAULT_MAX_TOOL_ROUNDS = 5

# Low-information words skipped when echoing a memory-topic FTS fallback query.
_FTS_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "about", "of", "for", "on", "in", "with",
    "what", "did", "say", "do", "is", "was", "were", "i", "you",
})


class AIService:
    """Chat facade. Owns session history and the provider, publishes ai.* events."""

    def __init__(
        self,
        provider: Optional[AIProvider] = None,
        event_bus: Optional[EventBus] = None,
        memory_service: Any = None,
        context_builder: Optional[ContextBuilder] = None,
        context_engine: Optional[ContextEngine] = None,
        max_history: int = DEFAULT_MAX_HISTORY,
        tool_registry: Optional[ToolRegistry] = None,
        tool_executor: Optional[ToolExecutor] = None,
        max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
        max_memory: int = 5,
        max_memory_chars: int = 1500,
        memory_retriever: Optional[Any] = None,
        intent_reasoner: Optional[IntentReasoner] = None,
    ) -> None:
        self._provider = provider or EchoProvider()
        self._event_bus = event_bus
        self._memory_service = memory_service
        self._context_builder = context_builder or ContextBuilder()
        self._max_history = max_history
        self._tool_registry = tool_registry
        self._tool_executor = tool_executor
        self._max_tool_rounds = max_tool_rounds
        self._max_memory = max_memory
        self._max_memory_chars = max_memory_chars
        self._memory_retriever = memory_retriever
        self._intent_reasoner = intent_reasoner
        self._tool_uses: List[str] = []

        if context_engine is None:
            context_engine = ContextEngine(
                system_prompt=self._context_builder.system_prompt,
                memory_service=memory_service,
                max_memory=max_memory,
                max_memory_chars=max_memory_chars,
                memory_retriever=memory_retriever,
            )
        self._context_engine = context_engine

        self._state = AIState.IDLE
        self._state_lock = threading.RLock()
        self._sessions: Dict[str, List[ChatMessage]] = {}
        # M1 Memory UX: reconstructed work session injected into the next
        # chat call so the provider sees what the user was working on.
        self._session_context: Optional[str] = None

    # ── State / provider introspection ──────────────────────────────

    @property
    def state(self) -> AIState:
        return self._state

    @property
    def provider_name(self) -> str:
        return self._provider.name

    @property
    def provider_available(self) -> bool:
        try:
            return self._provider.available
        except Exception:  # pragma: no cover - defensive
            return False

    def history(self, session_id: str = "default") -> List[ChatMessage]:
        """Full message history for a session (read-only copy)."""
        return list(self._sessions.get(session_id, []))

    def reset_session(self, session_id: str = "default") -> None:
        self._sessions.pop(session_id, None)

    # ── Work session injection (M1 Memory UX) ───────────────────────

    def inject_session_context(self, session: Optional[Dict[str, Any]]) -> None:
        """Inject the reconstructed work session into the next chat call.

        Called on boot when ``memory.session.restored`` fires. The session
        text is placed as an extra system message before the user's first
        message, so the provider sees what the user was working on without
        the user re-explaining it. A falsy/empty session is a no-op.
        """
        if not session:
            return
        summary = str(session.get("summary") or "").strip()
        if not summary:
            return
        facts = session.get("key_facts") or []
        parts = [f"The user was working on: {summary}."]
        if facts:
            parts.append("Remembered facts: " + "; ".join(facts) + ".")
        parts.append("Continue helping without requiring the user to re-explain this context.")
        self._session_context = " ".join(parts)

    # ── Tool integration ───────────────────────────────────────────

    @property
    def tool_registry(self) -> Optional[ToolRegistry]:
        return self._tool_registry

    @property
    def intent_reasoner(self) -> Optional[IntentReasoner]:
        return self._intent_reasoner

    def execute_tool(self, name: str, args: Optional[Dict[str, Any]] = None) -> ToolResult:
        """Execute a whitelisted tool through the injected ToolExecutor.

        Returns a structured ToolResult; never raises for command failures.
        Tool names are recorded for the per-turn TaskContext.
        """
        if self._tool_executor is None:
            return ToolResult(success=False, error="tool execution not configured", tool=name)
        self._tool_uses.append(name)
        return self._tool_executor.execute(name, args)

    # ── Chat API ────────────────────────────────────────────────────

    def chat(self, message: str, session_id: str = "default") -> AIResult:
        """Send a message and return the assistant's full reply.

        Publishes ai.thinking.started / ai.thinking.completed /
        ai.response.ready on the EventBus.
        """
        message = (message or "").strip()
        if not message:
            return AIResult(
                text="", session_id=session_id, state=AIState.ERROR,
                provider=self._provider.name,
            )

        if not self.provider_available:
            # Provider is unavailable — short-circuit before touching history.
            self._set_state(AIState.ERROR)
            self._emit(EventType.AI_ERROR, {
                "session_id": session_id, "message": message,
                "error": "provider_unavailable",
            })
            self._emit(EventType.AI_RESPONSE_READY, {
                "session_id": session_id, "message": message,
                "error": "provider_unavailable",
            })
            return AIResult(
                text="", session_id=session_id, state=AIState.ERROR,
                provider=self._provider.name,
            )

        start = time.perf_counter()
        self._set_state(AIState.THINKING)
        self._emit(EventType.AI_THINKING_STARTED, {
            "session_id": session_id, "message": message,
        })

        self._tool_uses = []
        history = self._sessions.setdefault(session_id, [])
        history.append(ChatMessage(role=ChatRole.USER, content=message))
        del history[:-self._max_history]

        context = self._context_engine.build(
            history,
            query=message,
            limit=self._max_memory,
            tool_round=0,
            recent_tools=[],
        )

        # ── Phase 3.3: Intent routing (when enabled). ──
        # The reasoner decides a route. It never executes tools; ACTION,
        # QUESTION and UNKNOWN fall through to the existing agent loop below
        # exactly as pre-3.3. Any failure degrades to the agent loop.
        short_circuit = self._try_intent_short_circuit(message, context, session_id)
        if short_circuit is not None:
            return short_circuit

        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=context.system_prompt),
            *context.messages,
        ]
        if self._session_context:
            messages.insert(1, ChatMessage(role=ChatRole.SYSTEM, content=self._session_context))

        try:
            self._set_state(AIState.RESPONDING)
            text, tool_rounds = self._run_agent_loop(messages, session_id)
        except Exception as exc:
            logger.exception("AI chat failed")
            error = str(exc) or type(exc).__name__
            self._set_state(AIState.ERROR)
            self._emit(EventType.AI_ERROR, {
                "session_id": session_id, "message": message, "error": error,
            })
            self._emit(EventType.AI_RESPONSE_READY, {
                "session_id": session_id, "message": message, "error": error,
            })
            return AIResult(
                text="", session_id=session_id, state=AIState.ERROR,
                provider=self._provider.name,
            )

        if context.task is not None:
            # Reflect the actual tool activity on the returned context.
            context.task.tool_round = tool_rounds
            context.task.recent_tools = list(self._tool_uses)
        history.append(ChatMessage(role=ChatRole.ASSISTANT, content=text))
        duration_ms = (time.perf_counter() - start) * 1000.0

        self._emit(EventType.AI_THINKING_COMPLETED, {
            "session_id": session_id, "duration_ms": duration_ms,
        })
        self._emit(EventType.AI_RESPONSE_READY, {
            "session_id": session_id, "message": message, "response": text,
        })
        self._set_state(AIState.IDLE)

        return AIResult(
            text=text,
            session_id=session_id,
            provider=self._provider.name,
            duration_ms=duration_ms,
            state=AIState.IDLE,
            context=context,
            tool_rounds=tool_rounds,
        )

    def _try_intent_short_circuit(
        self, message: str, context: Any, session_id: str
    ) -> Optional[AIResult]:
        """Route a message via the intent layer when enabled.

        Returns an AIResult to short-circuit the agent loop, or None to let
        the normal agent loop run.  Phase 3.3 safety:
          - The reasoner never executes tools; it only routes.
          - Only explicit MEMORY_WRITE stores memory (remember/... as ...).
          - ACTION / QUESTION / UNKNOWN fall through (return None).
          - Any failure → None → agent loop (Phase 3.2 behavior).
        """
        reasoner = self._intent_reasoner
        if reasoner is None:
            return None
        try:
            decision = reasoner.reason(
                user_message=message,
                context=context,
                available_tools=self._tool_registry.all() if self._tool_registry else [],
                recent_history=context.messages if context else None,
            )
        except Exception:  # pragma: no cover - defensive
            logger.warning("Intent routing failed; running agent loop")
            return None

        self._emit(EventType.INTENT_RESOLVED, {
            "session_id": session_id,
            "intent": decision.intent.value,
            "confidence": decision.confidence,
            "reason": decision.reason,
            "suggested_action": decision.suggested_action,
        })

        if decision.suggested_action == ACT_MEMORY_WRITE:
            return self._handle_memory_write(decision, message, session_id, context)
        if decision.suggested_action == ACT_MEMORY_SEARCH:
            prefetched = self._prefetch_memory(context, decision.extracted_params)
            context.memory = prefetched.memory if prefetched is not None else context.memory
            return None  # fall through to agent loop with enriched memory
        if decision.suggested_action == ACT_ASK_CLARIFICATION:
            return self._handle_clarification(decision, message, session_id, context)
        return None  # ACTION / QUESTION / UNKNOWN → agent loop

    def _handle_memory_write(
        self, decision: Any, message: str, session_id: str, context: Any
    ) -> AIResult:
        """Store an explicit memory write from a MEMORY_WRITE decision."""
        reasoner = self._intent_reasoner
        history = self._sessions.setdefault(session_id, [])
        start = time.perf_counter()

        record_id = reasoner.remember(decision.extracted_params) if reasoner else None
        if record_id:
            text = f"บันทึกเรียบร้อย: {decision.extracted_params.get('memory_key')}"
        else:
            text = "ไม่สามารถบันทึกหน่วยความจำได้"

        history.append(ChatMessage(role=ChatRole.ASSISTANT, content=text))
        duration_ms = (time.perf_counter() - start) * 1000.0

        self._emit(EventType.AI_THINKING_COMPLETED, {
            "session_id": session_id, "duration_ms": duration_ms,
        })
        self._emit(EventType.AI_RESPONSE_READY, {
            "session_id": session_id, "message": message, "response": text,
        })
        self._set_state(AIState.IDLE)

        return AIResult(
            text=text,
            session_id=session_id,
            provider=self._provider.name,
            duration_ms=duration_ms,
            state=AIState.IDLE,
            context=context,
            tool_rounds=0,
        )

    def _prefetch_memory(self, context: Any, params: Dict[str, Any]) -> Any:
        """Enrich context with extra memory before the agent loop runs."""
        retriever = self._memory_retriever
        if retriever is None or context is None or context.memory is None:
            return context
        query = (params or {}).get("memory_query") or (params or {}).get("query_topic", "")
        if not query:
            return context
        try:
            ranked = retriever.retrieve(query, limit=3, token_budget=500)
            # FTS5 is finicky with multi-word phrases ("the budget" → 0). If
            # the full topic returned nothing, retry with significant tokens.
            if not ranked:
                keys = [t for t in re.split(r"[\s,;.!?]+", query)
                        if t.strip() and t.lower() not in _FTS_STOPWORDS]
                for key in keys:
                    ranked = retriever.retrieve(key, limit=3, token_budget=500)
                    if ranked:
                        break
        except Exception:  # pragma: no cover - defensive
            logger.warning("Memory pre-fetch failed")
            return context

        merged: Dict[str, Any] = {}
        for rec in context.memory.relevant:
            merged[str(rec.get("id", ""))] = rec
        for r in ranked:
            view = r.memory
            merged[str(view.get("id", ""))] = view

        context.memory = MemoryContext(
            relevant=list(merged.values()),
            stats=context.memory.stats,
            budget=context.memory.budget,
            skipped_due_to_budget=context.memory.skipped_due_to_budget,
        )
        return context

    def _handle_clarification(
        self, decision: Any, message: str, session_id: str, context: Any
    ) -> AIResult:
        """Return a follow-up prompt for a CLARIFICATION decision."""
        reasoner = self._intent_reasoner
        text = reasoner.clarify_text(decision) if reasoner else \
            "ขอให้ผมช่วยอะไรเพิ่มเติมไหมครับ?"
        history = self._sessions.setdefault(session_id, [])
        history.append(ChatMessage(role=ChatRole.ASSISTANT, content=text))

        self._emit(EventType.AI_RESPONSE_READY, {
            "session_id": session_id, "message": message, "response": text,
        })
        self._set_state(AIState.IDLE)

        return AIResult(
            text=text,
            session_id=session_id,
            provider=self._provider.name,
            state=AIState.IDLE,
            context=context,
            tool_rounds=0,
        )

    def _run_agent_loop(
        self, messages: List[ChatMessage], session_id: str
    ) -> Tuple[str, int]:
        """Run the bounded agent loop: provider ↔ tools until the model stops.

        Contract:
          - Max ``max_tool_rounds`` tool-calling rounds; exceeding it raises
            ProviderError (mapped to AIState.ERROR by chat()).
          - Tool calls/results are transient: they only exist in the per-turn
            message list handed to the provider and are never written to
            session history.
        """
        tools = self._tool_registry.all() if self._tool_registry else []
        rounds = 0
        while True:
            response = self._provider.respond(messages, tools)
            if not response.tool_calls:
                return response.text, rounds

            rounds += 1
            if rounds > self._max_tool_rounds:
                raise ProviderError(
                    f"max tool rounds exceeded ({self._max_tool_rounds})"
                )

            messages.append(ChatMessage(
                role=ChatRole.ASSISTANT,
                content=response.text,
                tool_calls=list(response.tool_calls),
            ))
            for call in response.tool_calls:
                tool_start = time.perf_counter()
                self._emit(EventType.AI_TOOL_STARTED, {
                    "session_id": session_id, "tool": call.name,
                    "arguments": call.arguments,
                })
                result = self.execute_tool(call.name, call.arguments)
                duration_ms = (time.perf_counter() - tool_start) * 1000.0
                self._emit(EventType.AI_TOOL_COMPLETED, {
                    "session_id": session_id, "tool": call.name,
                    "success": result.success, "duration_ms": duration_ms,
                })
                messages.append(ChatMessage(
                    role=ChatRole.TOOL,
                    content=json.dumps(result.to_dict(), ensure_ascii=False),
                    tool_call_id=call.id,
                ))

    def stream(self, message: str, session_id: str = "default") -> Iterator[StreamEvent]:
        """Yield StreamEvent objects describing the response stream.

        Contract (Phase 1.5, internal only):
            started → delta... → completed
            started → error

        Phase 1 providers are single-chunk; a token-streaming provider plugs
        in later without changing this API.
        """
        yield StreamEvent.started(session_id=session_id)
        result = self.chat(message, session_id)
        if result.state == AIState.ERROR:
            yield StreamEvent.error("provider failed", session_id=session_id)
            return
        yield StreamEvent.delta(result.text, session_id=session_id)
        yield StreamEvent.completed(result.text, session_id=session_id)

    # ── Event emission ──────────────────────────────────────────────

    def _set_state(self, state: AIState) -> None:
        with self._state_lock:
            self._state = state
        self._emit(EventType.AI_STATE_CHANGED, {"state": state.value})

    def _emit(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        if self._event_bus:
            try:
                self._event_bus.publish(
                    Event(type=event_type, payload=payload, source=EVENT_SOURCE)
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Failed to publish %s: %s", event_type, e)
