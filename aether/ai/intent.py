"""Intent / Reasoning — explicit routing between the context and the agent loop.

Phase 3.3 scope:
  - ``IntentType`` taxonomy: QUESTION / MEMORY_RETRIEVAL / MEMORY_WRITE /
    ACTION / CLARIFICATION / UNKNOWN.
  - ``IntentDecision``: explainable classification (intent + confidence +
    reason + extracted_params + suggested_action).  ``confidence`` is metadata
    for observability only — routing is deterministic rule priority, never a
    confidence threshold.
  - ``RuleBasedIntentClassifier``: deterministic, no LLM call, no I/O.
    MEMORY_WRITE is only triggered by explicit "remember/store ... as ..."
    commands — general statements are never auto-saved.
  - ``IntentReasoner``: routing layer, not a second agent.  It only decides a
    route; it never executes tools, and ACTION / QUESTION / UNKNOWN fall
    through to the existing agent loop untouched.

Scope guards (Phase 3.3):
  - No Agent Loop rewrite, no Provider API change, no extra LLM.
  - No arbitrary CommandBus execution from this module.
  - No memory auto-save.
  - No confidence-based routing thresholds.
  - Vision/CV freeze: this module never touches the computer-vision subsystem
    (it remains fully decoupled from the AI layer).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("Aether.AI.Intent")


class IntentType(str, Enum):
    """The six intents Aether can recognize in a user message."""

    QUESTION = "question"            # General Q&A → run agent loop
    MEMORY_RETRIEVAL = "memory_retrieval"  # "What did I say about X?" → prefetch
    MEMORY_WRITE = "memory_write"    # explicit "remember X as Y" → remember()
    ACTION = "action"                # "open the memory panel" → run agent loop
    CLARIFICATION = "clarification"  # ambiguous / too short → ask follow-up
    UNKNOWN = "unknown"              # default → run agent loop


# Suggested actions the reasoner can return (deterministic).
ACT_RUN_AGENT_LOOP = "run_agent_loop"
ACT_MEMORY_WRITE = "memory_write"
ACT_MEMORY_SEARCH = "memory_search"
ACT_ASK_CLARIFICATION = "ask_clarification"

DEFAULT_CLARIFICATION = "ขอให้ผมช่วยอะไรเพิ่มเติมไหมครับ?"

# Regex settings for the data-driven rule table.
_RE_IGNORECASE = re.IGNORECASE

# Default importance for an explicit memory write with no stated importance.
_DEFAULT_WRITE_IMPORTANCE = 0.8


@dataclass(frozen=True)
class IntentDecision:
    """An explainable classification of a user message.

    ``confidence`` is informational only.  ``suggested_action`` is the
    deterministic routing result; routing NEVER consults ``confidence``.
    """

    intent: IntentType
    confidence: float
    reason: str
    suggested_action: str = ACT_RUN_AGENT_LOOP
    extracted_params: Dict[str, Any] = field(default_factory=dict)


# ── Classifier protocol ─────────────────────────────────────────────────


class IntentClassifier:
    """Routes a user message to an IntentDecision.

    Implementations are deterministic and never raise; they degrade to
    ``UNKNOWN`` on any failure so the chat flow is never blocked.
    """

    def classify(
        self,
        user_message: str,
        context: Any = None,
        available_tools: Optional[Sequence[Any]] = None,
        recent_history: Optional[Sequence[Any]] = None,
    ) -> IntentDecision:
        raise NotImplementedError


# ── Rule table ──────────────────────────────────────────────────────────

# Each entry: (pattern, intent, suggested_action, extractor)
# extractor(match) -> (reason, extracted_params)
_Rule = Tuple[str, IntentType, str, Callable[[re.Match], Tuple[str, Dict[str, Any]]]]


def _mem_write(m: re.Match) -> Tuple[str, Dict[str, Any]]:
    key = m.group("key").strip()
    value = m.group("value").strip()
    return (
        f"explicit memory write: '{key}'",
        {"memory_key": key, "memory_value": value, "importance": _DEFAULT_WRITE_IMPORTANCE},
    )


def _mem_retrieve_about(m: re.Match) -> Tuple[str, Dict[str, Any]]:
    topic = m.group("topic").strip()
    return (
        f"memory retrieval about '{topic}'",
        {"query_topic": topic, "memory_query": topic},
    )


def _mem_retrieve_thai(m: re.Match) -> Tuple[str, Dict[str, Any]]:
    topic = m.group("topic").strip()
    return (
        f"memory retrieval about '{topic}'",
        {"query_topic": topic, "memory_query": topic},
    )


def _mem_write_thai(m: re.Match) -> Tuple[str, Dict[str, Any]]:
    statement = m.group("statement").strip()
    if not statement:
        return (
            "explicit memory write (empty)",
            {"memory_key": "", "memory_value": "", "importance": _DEFAULT_WRITE_IMPORTANCE},
        )
    key = statement.split()[:4]
    key = " ".join(key) + "…" if len(key) >= 4 else statement
    return (
        f"explicit memory write: '{statement}'",
        {"memory_key": key, "memory_value": statement, "importance": _DEFAULT_WRITE_IMPORTANCE},
    )


def _mem_retrieve(m: re.Match) -> Tuple[str, Dict[str, Any]]:
    topic = m.group("topic").strip()
    return (
        f"memory retrieval: '{topic}'",
        {"query_topic": topic, "memory_query": topic},
    )


def _action(m: re.Match) -> Tuple[str, Dict[str, Any]]:
    verb = m.group("verb").lower()
    target = m.group("target").strip().lower()
    tool_hint = _tool_hint_for(verb, target)
    return (
        f"imperative action '{verb} {target}'",
        {"tool_hint": tool_hint, "verb": verb, "target": target},
    )


# Imperative verbs the ACTION classifier reacts to.  These still fall through
# to the agent loop — the tool hint only goes into extracted_params for
# observability; it is NOT executed by the intent layer.
_ACTION_VERBS = (
    "open", "close", "toggle", "show", "hide",
    "create", "delete", "start", "stop", "run",
    # Thai
    "เปิด", "ปิด", "แสดง", "ซ่อน", "เริ่ม", "หยุด",
)

# Map a (verb, target) to a best-effort tool hint (informational only).
_TOOL_HINTS = {
    ("open", "memory"): "memory.recall",
    ("open", "memory panel"): "ui.panel.toggle",
    ("close", "memory"): "ui.panel.toggle",
    ("show", "memory"): "memory.search",
    ("toggle", "panel"): "ui.panel.toggle",
}


def _tool_hint_for(verb: str, target: str) -> Optional[str]:
    for (v, t), hint in _TOOL_HINTS.items():
        if v == verb and (t == target or target in t or t in target):
            return hint
    return None


_RULES: List[_Rule] = [
    # 0. Thai explicit memory write: "จำไว้ว่า <statement>" (no space required)
    (
        r"^\s*จ[ำั]ไว้ว่า\s*(?P<statement>.+?)\s*[.!?]*$",
        IntentType.MEMORY_WRITE,
        ACT_MEMORY_WRITE,
        _mem_write_thai,
    ),
    # 1. Explicit memory write — REQUIRED by safety constraint 2. This is the
    #    ONLY path to remember(). General statements never auto-save.
    (
        r"^\s*(?:remember|store)\s+(?P<key>.+?)\s+as\s+(?P<value>.+?)\s*[.!?]*$",
        IntentType.MEMORY_WRITE,
        ACT_MEMORY_WRITE,
        _mem_write,
    ),
    # 2. "what did you/I say about <topic>?"
    (
        r"^\s*(?:what|who|when|where|why|how)\s+(?:did|do|is|was|were)"
        r"\s+(?:you|i|we|it)\s+(?:say|remember|know|mention)\s+about\s+(?P<topic>.+?)\s*[?]*$",
        IntentType.MEMORY_RETRIEVAL,
        ACT_MEMORY_SEARCH,
        _mem_retrieve_about,
    ),
    # 2b. Thai memory retrieval: "ฉันเคยบอกอะไรเกี่ยวกับ <topic>?"
    (
        r"^\s*(?:ฉัน|ผม)?\s*เคย(?:บอก|พูด|กล่[าาว]|ล่[าาว])?\s*(?:อะไร|ยังไง|ไหม)?\s*เกี่ยวกับ\s*(?P<topic>.+?)\s*[?]*$",
        IntentType.MEMORY_RETRIEVAL,
        ACT_MEMORY_SEARCH,
        _mem_retrieve_thai,
    ),
    # 3. "search/recall/find memory about <topic>"
    (
        r"^\s*(?:search|recall|find|retrieve)\s+(?:memory|fact|info)"
        r"\s+(?:about|for|on)\s+(?P<topic>.+?)\s*[?]*$",
        IntentType.MEMORY_RETRIEVAL,
        ACT_MEMORY_SEARCH,
        _mem_retrieve,
    ),
    # 4. Imperative action: "<verb> the <target>"
    (
        r"^\s*(?P<verb>" + "|".join(_ACTION_VERBS) + r")\s+(?:the\s+)?(?P<target>[^.?]+)\s*[.!]?$",
        IntentType.ACTION,
        ACT_RUN_AGENT_LOOP,
        _action,
    ),
]


class RuleBasedIntentClassifier(IntentClassifier):
    """Deterministic, explainable classifier using a data-driven rule table.

    Rules are checked in priority order; the first match wins.  No LLM call,
    no I/O, no confidence threshold — the winning rule determines routing.
    """

    def __init__(self, rules: Optional[List[_Rule]] = None) -> None:
        self._rules: List[Tuple[re.Pattern, IntentType, str, Callable]] = []
        for pattern, intent, action, extractor in (rules if rules is not None else _RULES):
            try:
                compiled = re.compile(pattern, _RE_IGNORECASE)
            except re.error as exc:  # pragma: no cover - defensive
                logger.warning("Skipping invalid intent rule %r: %s", pattern, exc)
                continue
            self._rules.append((compiled, intent, action, extractor))

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    def classify(
        self,
        user_message: str,
        context: Any = None,
        available_tools: Optional[Sequence[Any]] = None,
        recent_history: Optional[Sequence[Any]] = None,
    ) -> IntentDecision:
        try:
            raw = (user_message or "").strip()
            # Normalize to NFC so decomposed Thai (e.g. ํ + า vs ำ) matches
            # the precomposed literals in the rule table consistently.
            text = unicodedata.normalize("NFC", raw)
            if not text:
                return StrategyMetrics.default_decision(IntentType.CLARIFICATION,
                                                         "empty message")
            for compiled, intent, action, extractor in self._rules:
                m = compiled.match(text)
                if m is not None:
                    reason, params = extractor(m)
                    return IntentDecision(
                        intent=intent,
                        confidence=StrategyMetrics.rule_confidence(intent),
                        reason=reason,
                        suggested_action=action,
                        extracted_params=params,
                    )
            # Decision on un-matched messages (deterministic — no threshold).
            return _classify_unmatched(text)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Intent classification failed (%s); defaulting", exc)
            return StrategyMetrics.default_decision(IntentType.UNKNOWN,
                                                    "classification error")


class StrategyMetrics:
    """Deterministic confidence labels (informational only)."""

    @staticmethod
    def rule_confidence(intent: IntentType) -> float:
        return {
            IntentType.MEMORY_WRITE: 0.95,
            IntentType.MEMORY_RETRIEVAL: 0.92,
            IntentType.ACTION: 0.85,
            IntentType.CLARIFICATION: 0.55,
            IntentType.QUESTION: 0.60,
            IntentType.UNKNOWN: 0.50,
        }.get(intent, 0.50)

    @staticmethod
    def default_decision(intent: IntentType, reason: str) -> IntentDecision:
        action = _action_for(intent)
        return IntentDecision(
            intent=intent,
            confidence=StrategyMetrics.rule_confidence(intent),
            reason=reason,
            suggested_action=action,
        )


def _action_for(intent: IntentType) -> str:
    return {
        IntentType.MEMORY_WRITE: ACT_MEMORY_WRITE,
        IntentType.MEMORY_RETRIEVAL: ACT_MEMORY_SEARCH,
        IntentType.CLARIFICATION: ACT_ASK_CLARIFICATION,
        IntentType.ACTION: ACT_RUN_AGENT_LOOP,
        IntentType.QUESTION: ACT_RUN_AGENT_LOOP,
        IntentType.UNKNOWN: ACT_RUN_AGENT_LOOP,
    }[intent]


def _classify_unmatched(text: str) -> IntentDecision:
    """Fallback for messages that match no rule. Deterministic.

    - Ends with '?' → QUESTION (run agent loop).
    - Is a genuinely ambiguous filler word → CLARIFICATION (ask follow-up).
    - Otherwise → UNKNOWN (run agent loop), so the model handles it — this
      keeps greetings and short commands flowing through the agent loop as
      they did pre-3.3.
    """
    if text.endswith("?"):
        return StrategyMetrics.default_decision(IntentType.QUESTION,
                                                "ends with a question mark")
    if text in _AMBIGUOUS_FILLERS:
        return StrategyMetrics.default_decision(
            IntentType.CLARIFICATION, "ambiguous filler"
        )
    return StrategyMetrics.default_decision(IntentType.UNKNOWN,
                                            "no rule matched")


# Words that are genuinely ambiguous on their own (not greetings/commands).
_AMBIGUOUS_FILLERS = frozenset({
    "เอ่อ", "ครับ", "ค่ะ", "อืม", "hmm", "um", "uh",
})


# ── IntentReasoner ──────────────────────────────────────────────────────


class IntentReasoner:
    """Routes a user message through the intent pipeline.

    This is a ROUTING layer, not a second agent.  It decides a route and — for
    the explicit MEMORY_WRITE path — stores memory via the injected retriever.
    It never executes tools and never touches the CommandBus.  ACTION,
    QUESTION and UNKNOWN simply route back to ``run_agent_loop`` so the
    existing agent loop handles them exactly as it does today.

    Degradation: any failure returns a decision of ``UNKNOWN`` /
    ``run_agent_loop`` so the caller falls through to Phase 3.2 behavior —
    the chat never breaks because of the intent layer.
    """

    def __init__(
        self,
        classifier: Optional[IntentClassifier] = None,
        memory_retriever: Any = None,
        max_clarification_turns: int = 2,
    ) -> None:
        self._classifier = classifier or RuleBasedIntentClassifier()
        self._memory_retriever = memory_retriever
        self._max_clarification_turns = max_clarification_turns

    @property
    def classifier(self) -> IntentClassifier:
        return self._classifier

    @property
    def memory_retriever(self) -> Any:
        return self._memory_retriever

    @property
    def max_clarification_turns(self) -> int:
        return self._max_clarification_turns

    def reason(
        self,
        user_message: str,
        context: Any = None,
        available_tools: Optional[Sequence[Any]] = None,
        recent_history: Optional[Sequence[Any]] = None,
    ) -> IntentDecision:
        try:
            return self._classifier.classify(
                user_message,
                context=context,
                available_tools=available_tools,
                recent_history=recent_history,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Intent reasoning failed (%s); routing to agent loop", exc)
            return StrategyMetrics.default_decision(IntentType.UNKNOWN,
                                                    "reasoning failure")

    def remember(self, params: Dict[str, Any]) -> Optional[str]:
        """Store an explicitly requested memory write. Returns record id or None.

        Called only for MEMORY_WRITE decisions that carry memory_key/value.
        Never auto-saves; never infers a write from a general statement.
        """
        if self._memory_retriever is None:
            logger.warning("IntentReasoner.remember: no memory retriever")
            return None
        key = (params or {}).get("memory_key")
        value = (params or {}).get("memory_value")
        importance = float((params or {}).get("importance", _DEFAULT_WRITE_IMPORTANCE))
        key = (key or "").strip()
        if not key:
            logger.warning("IntentReasoner.remember: empty memory key")
            return None
        try:
            return self._memory_retriever.remember(key, value, importance=importance)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("IntentReasoner.remember failed: %s", exc)
            return None

    def clarify_text(self, decision: IntentDecision) -> str:
        """Return the follow-up prompt for a CLARIFICATION decision."""
        intent = decision.intent.value if decision.intent else ""
        prompts = {
            "question": "ขอให้ผมช่วยอะไรเพิ่มเติมไหมครับ?",
            "action": "ต้องการให้ผมทำอะไรครับ?",
            "memory_retrieval": "ต้องการให้ผมหาอะไรในหน่วยความจำครับ?",
            "memory_write": "ต้องการให้ผมจำอะไรครับ?",
        }
        return prompts.get(intent, DEFAULT_CLARIFICATION)
