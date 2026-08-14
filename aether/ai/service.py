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
import threading
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

from aether.ai.context import ContextBuilder, ContextEngine
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
        self._tool_uses: List[str] = []

        if context_engine is None:
            context_engine = ContextEngine(
                system_prompt=self._context_builder.system_prompt,
                memory_service=memory_service,
                max_memory=max_memory,
            )
        self._context_engine = context_engine

        self._state = AIState.IDLE
        self._state_lock = threading.RLock()
        self._sessions: Dict[str, List[ChatMessage]] = {}

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

    # ── Tool integration ───────────────────────────────────────────

    @property
    def tool_registry(self) -> Optional[ToolRegistry]:
        return self._tool_registry

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
        messages = [
            ChatMessage(role=ChatRole.SYSTEM, content=context.system_prompt),
            *context.messages,
        ]

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
