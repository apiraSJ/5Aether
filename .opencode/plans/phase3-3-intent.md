# Phase 3.3 Intent / Reasoning — Plan

**Status:** PLAN MODE (read-only — no implementation)

**Parent checkpoint:** `v1.0.0-memory-contract-stable` (commit 3ad8595)

---

## 1. Problem Statement

The current `AIService.chat()` flow:
```
User message → ContextEngine.build() → _run_agent_loop() (provider ↔ tools) → response
```

The provider (Echo/LLM) receives the full context + tool list and decides **implicitly** whether to:
- Answer directly
- Call a tool
- Ask for clarification

This is **opaque** and **uncontrollable**:
- No visibility into *why* the model chose a tool
- No way to pre-fetch memory for memory-heavy queries
- No explicit memory-write path (currently only via tool `memory.recall`)
- No structured clarification flow

**Goal:** Insert an explicit **Intent/Reasoning layer** that classifies the user's message *before* the agent loop, enabling deterministic routing and observability — **without replacing the Agent Loop**.

---

## 2. Design Principles

| Principle | Application |
|-----------|-------------|
| **No Agent Loop rewrite** | `_run_agent_loop()` stays; Intent layer sits *before* it |
| **No new frameworks** | No LangGraph/CrewAI/smolagents — pure Python, pluggable |
| **Deterministic by default** | Rule-based classifier first; LLM fallback optional, configurable |
| **Explainable** | Every decision exposes `reason`, `confidence`, `extracted_params` |
| **Preserve Vision freeze** | `aether/ai/**` never imports CV stack |
| **Storage-agnostic** | Uses existing `MemoryRetriever` protocol, not direct DB |
| **Testable** | Pure functions, no I/O in core logic |

## 2.1 Safety Constraints (Locked)

| Constraint | Enforcement |
|------------|-------------|
| **IntentReasoner is a routing layer, not a second agent** | `ACTION`, `QUESTION`, `UNKNOWN` → **must** route to existing `_run_agent_loop()`; no arbitrary CommandBus execution from Intent layer |
| **MEMORY_WRITE requires explicit user command** | Only `^remember\s+.+\s+as\s+.+$` / `^store\s+.+\s+as\s+.+$` patterns trigger `retriever.remember()`; general statements like "I like dark UI" **never** auto-save |
| **Confidence is metadata, not a routing threshold** | `confidence` stored in `IntentDecision` for observability; **no** `if confidence < X: ...` logic in Phase 3.3; deterministic rule priority only |
| **Degradation = exact Phase 3.2 behavior** | Any Intent layer failure (exception, missing retriever, config disabled) → log warning → fall through to unmodified `_run_agent_loop()` with original context |

---

## 3. Intent Taxonomy

```python
class IntentType(str, Enum):
    QUESTION        = "question"          # General Q&A → run agent loop (or direct answer)
    MEMORY_RETRIEVAL = "memory_retrieval" # "What did I say about X?" → pre-fetch memory, then agent loop
    MEMORY_WRITE    = "memory_write"      # "Remember that Y=Z" → retriever.remember(), confirm
    ACTION          = "action"            # "Open panel X" → run agent loop with tool hint
    CLARIFICATION   = "clarification"     # Ambiguous → ask user follow-up
    UNKNOWN         = "unknown"           # Fallback → run agent loop
```

**NOT an intent:** `VISION_QUERY` — Vision is frozen; if OverlayModel is present, VisionContext is already in the prompt.

---

## 4. Core Contracts

### 4.1 `IntentDecision`

```python
@dataclass(frozen=True)
class IntentDecision:
    intent: IntentType
    confidence: float              # 0.0..1.0
    reason: str                    # Human-readable explanation
    extracted_params: Dict[str, Any]  # e.g. {"memory_key": "project name", "tool_hint": "ui.panel.toggle"}
    suggested_action: str          # "run_agent_loop" | "memory_search" | "memory_write" | "ask_clarification" | "direct_answer"
```

### 4.2 `IntentClassifier` Protocol

```python
class IntentClassifier(Protocol):
    def classify(
        self,
        user_message: str,
        context: AIContext,        # Full context (system/workspace/memory/task/vision)
        available_tools: List[ToolDef],
        recent_history: List[ChatMessage],
    ) -> IntentDecision:
        ...
```

### 4.3 `IntentReasoner` — Orchestrator

```python
class IntentReasoner:
    """Routes a user message through the intent pipeline."""

    def __init__(
        self,
        classifier: IntentClassifier,
        memory_retriever: Optional[MemoryRetriever] = None,
        max_clarification_turns: int = 2,
    ) -> None:
        ...

    def reason(
        self,
        user_message: str,
        context: AIContext,
        available_tools: List[ToolDef],
        recent_history: List[ChatMessage],
    ) -> IntentDecision:
        ...
```

---

## 5. Default Implementation: `RuleBasedIntentClassifier`

**No LLM call.** Pure Python, deterministic, explainable.

### 5.1 Classification Rules (priority order)

| Priority | Pattern | Intent | Params Extracted |
|----------|---------|--------|------------------|
| 1 | `^remember\s+(.+)\s+as\s+(.+)$` / `^store\s+(.+)\s+as\s+(.+)$` | `MEMORY_WRITE` | `memory_key`, `memory_value`, `importance` |
| 2 | `^(what|who|when|where|why|how)\s+(did|do|is|was|were)\s+(you|I|we)\s+(say|remember|know)\s+about\s+(.+)$` | `MEMORY_RETRIEVAL` | `query_topic` |
| 3 | `^(recall|search|find)\s+(memory|fact)\s+(.+)$` | `MEMORY_RETRIEVAL` | `query_topic` |
| 4 | Tool name match in message (fuzzy) | `ACTION` | `tool_hint` |
| 5 | Question mark `?` + no memory/action pattern | `QUESTION` | — |
| 6 | Imperative verb + noun (open, close, toggle, show, hide) | `ACTION` | `tool_hint` |
| 7 | Short message (< 4 tokens) + no clear pattern | `CLARIFICATION` | — |
| 8 | Default | `UNKNOWN` | — |

**Note:** Rules are data-driven (list of `(regex, intent, extractor_fn)`) for easy extension.

### 5.2 Confidence Heuristics

- Exact regex match: `0.95`
- Fuzzy tool name match (Levenshtein ≤ 2): `0.75`
- Keyword-only match: `0.60`
- Default: `0.50`

### 5.3 `extracted_params` Examples

```python
# "remember project codename as aether nexus"
{"memory_key": "project codename", "memory_value": "aether nexus", "importance": 0.8}

# "what did I say about the budget?"
{"query_topic": "budget"}

# "open the memory panel"
{"tool_hint": "ui.panel.toggle", "panel_id": "memory"}
```

---

## 6. Integration Point: `AIService.chat()`

**Minimal change** to `AIService.chat()`:

```python
def chat(self, message: str, session_id: str = "default") -> AIResult:
    # ... existing validation ...

    # 1. Build base context (as before)
    context = self._context_engine.build(...)

    # 2. NEW: Intent reasoning
    decision = self._intent_reasoner.reason(
        user_message=message,
        context=context,
        available_tools=self._tool_registry.all() if self._tool_registry else [],
        recent_history=history,
    )

    # 3. Route based on decision
    if decision.suggested_action == "memory_write":
        return self._handle_memory_write(decision, message, session_id)

    if decision.suggested_action == "memory_search":
        # Pre-fetch memory BEFORE agent loop
        context = self._prefetch_memory(context, decision.extracted_params)

    if decision.suggested_action == "ask_clarification":
        return self._handle_clarification(decision, message, session_id)

    # 4. Default: run agent loop (existing behavior)
    text, tool_rounds = self._run_agent_loop(messages, session_id)
    # ...
```

### 6.1 `_handle_memory_write()`

```python
def _handle_memory_write(self, decision, message, session_id):
    retriever = self._context_engine.memory_retriever
    if retriever is None:
        return AIResult(text="Memory not available", state=AIState.ERROR, ...)

    key = decision.extracted_params["memory_key"]
    value = decision.extracted_params["memory_value"]
    importance = decision.extracted_params.get("importance", 0.5)

    record_id = retriever.remember(key, value, importance=importance)
    if record_id:
        text = f"Remembered: {key} = {value}"
    else:
        text = "Failed to store memory"

    # Record in history, emit events, return AIResult
    ...
```

### 6.2 `_prefetch_memory()`

```python
def _prefetch_memory(self, context, params):
    """Inject additional memory into context before agent loop."""
    retriever = self._context_engine.memory_retriever
    if retriever is None:
        return context

    query = params.get("query_topic", "")
    extra = retriever.retrieve(query, limit=3, token_budget=500)

    # Merge into existing memory context (dedupe by id)
    merged = {r["id"]: r for r in context.memory.relevant}
    for r in extra:
        merged[r.memory["id"]] = r.memory

    new_memory_ctx = MemoryContext(
        relevant=list(merged.values()),
        stats=context.memory.stats,
        budget=context.memory.budget,
        skipped_due_to_budget=context.memory.skipped_due_to_budget,
    )
    return AIContext(..., memory=new_memory_ctx, ...)
```

### 6.3 `_handle_clarification()`

```python
def _handle_clarification(self, decision, message, session_id):
    clarification_prompts = {
        "question": "Could you clarify what you'd like to know?",
        "action": "What would you like me to do?",
        "memory": "What should I remember or look up?",
    }
    prompt = clarification_prompts.get(decision.intent.value, "Could you rephrase?")
    return AIResult(text=prompt, state=AIState.IDLE, context=context, ...)
```

---

## 7. Configuration

`config/ai.yaml` additions:

```yaml
ai:
  intent:
    enabled: true
    classifier: "rule_based"        # "rule_based" | "llm" (future)
    max_clarification_turns: 2
    rule_sets:                      # optional custom rule files
      - "config/intent/rules.yaml"
```

---

## 8. Event Bus Integration

Emit intent events for observability/debugging:

```python
# ai.intent.classified
{
    "session_id": "...",
    "intent": "memory_retrieval",
    "confidence": 0.92,
    "reason": "matched pattern: 'what did I say about (.+)'",
    "suggested_action": "memory_search",
}
```

---

## 9. Tests

| Test File | Coverage |
|-----------|----------|
| `tests/test_intent_classifier.py` | Unit: rule matching, confidence, param extraction for all 6 intent types |
| `tests/test_intent_reasoner.py` | Unit: routing logic, memory_write path, prefetch merge, clarification |
| `tests/test_ai_intent_integration.py` | Integration: AIService.chat() with IntentReasoner wired; end-to-end flows |
| `tests/test_vision_freeze.py` | Existing scan test must still pass (no CV imports in aether/ai/**) |

### Key Integration Scenarios

1. **Memory write explicit:** `"remember my name is John"` → `MEMORY_WRITE` → `retriever.remember()` → confirm
2. **Memory retrieval:** `"what did I say about the budget?"` → `MEMORY_RETRIEVAL` → prefetch → agent loop
3. **Action with tool hint:** `"open the memory panel"` → `ACTION` → agent loop (tool called)
4. **Clarification:** `"do it"` → `CLARIFICATION` → "What would you like me to do?"
5. **Question fallback:** `"what is the capital of France?"` → `QUESTION` → agent loop (no tools called)
6. **Unknown:** `"asdfghjkl"` → `UNKNOWN` → agent loop

---

## 10. Files Touched

| File | Change |
|------|--------|
| `aether/ai/intent.py` | **NEW** — `IntentType`, `IntentDecision`, `IntentClassifier`, `RuleBasedIntentClassifier`, `IntentReasoner` |
| `aether/ai/service.py` | Add `_intent_reasoner` field; wire into `chat()`; add routing helpers |
| `aether/plugins/ai_plugin.py` | Instantiate `IntentReasoner` + `RuleBasedIntentClassifier`; inject into `AIService` |
| `config/ai.yaml` | Add `ai.intent` config section |
| `tests/test_intent_classifier.py` | **NEW** |
| `tests/test_intent_reasoner.py` | **NEW** |
| `tests/test_ai_intent_integration.py` | **NEW** |

**NOT touched:** `aether/ai/context.py`, `aether/ai/memory.py`, `aether/ai/tools.py`, `aether/ai/provider.py`, `aether/core/command_bus.py`, Vision stack.

---

## 11. Rollback / Degradation

- If `IntentReasoner` raises → log warning, fall through to existing agent loop
- If `classifier` returns `UNKNOWN` → default to `run_agent_loop`
- If `memory_retriever` missing → `MEMORY_WRITE`/`MEMORY_RETRIEVAL` degrade to agent loop
- Config `ai.intent.enabled: false` → completely bypasses intent layer (backward compat)

---

## 12. Acceptance Criteria

1. **All existing tests pass** (847 → still ≥ 847)
2. **New tests pass** (intent classifier, reasoner, integration)
3. **Explicit memory write works:** `"remember X as Y"` stores via `retriever.remember()` without tool call
4. **Memory retrieval pre-fetch works:** `"what did I say about X?"` injects relevant memory before agent loop
5. **Clarification flow works:** Ambiguous short message returns a follow-up question
6. **Action routing works:** Tool-hint messages route to agent loop with correct tool available
7. **Vision freeze intact:** `grep -r "mediapipe\|ultralytics\|yolo\|cv2\|camera" aether/ai/**` returns nothing
8. **Performance:** Intent classification adds < 2ms (rule-based, no I/O)
9. **Config toggle works:** `ai.intent.enabled: false` restores pre-3.3 behavior exactly

### 12.1 Safety Constraint Verification

10. **IntentReasoner cannot execute arbitrary CommandBus commands** — only `MEMORY_WRITE` calls `retriever.remember()`; `ACTION`/`QUESTION`/`UNKNOWN` route to `_run_agent_loop()`
11. **Normal QUESTION / ACTION / UNKNOWN pass through Agent Loop** — no shortcuts, no direct tool execution from Intent layer
12. **Intent layer failure falls back to Phase 3.2 behavior** — exception or disabled config → identical chat() flow as pre-3.3
13. **No confidence-based routing thresholds** — `confidence` field exists for logging/debug only; routing is purely deterministic rule priority

---

## 13. Out of Scope (Explicitly Deferred)

| Item | Reason |
|------|--------|
| LLM-based classifier | Phase 4+; requires provider dependency |
| Multi-turn clarification state machine | Phase 4; current `max_clarification_turns` is a simple guard |
| Intent learning/feedback loop | Phase 5 |
| Complex planning (multi-step) | Phase 4; Agent Loop already does single-step tool calling |
| Vision intent | Vision is frozen |

---

## 14. Checkpoint

On approval: commit `feat: Phase 3.3 Intent Reasoning`, tag `v1.0.0-intent-stable`.

**Next:** Phase 3.4 Tools / Permissions (expand ToolRegistry with permission gates, user approval flow).