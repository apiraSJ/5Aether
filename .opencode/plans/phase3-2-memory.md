# Phase 3.2 — Memory Retriever Contract

**Status:** **Contract draft — awaiting human review** · NOT yet approved for implementation
**Depends on:** Phase 3.1 (Context Engine, 820 tests passing) · Phase 2 (AI foundation)
**Blocked by:** None

---

## Objective

Define a **stable MemoryRetriever contract** that gives the AI Runtime a reliable,
explainable way to retrieve and rank relevant memory. This is a **contract-first**
phase: we lock interfaces, data structures, ranking rules, budget policy, and
integration points **before** writing any implementation.

The goal is:

> Make Aether have a "memory contract" the AI Runtime can rely on — regardless of
> whether the underlying store uses SQLite, FTS5, embeddings, or anything else.

**No source code will be written in this phase.** Only this plan document, which
must survive human review before implementation begins.

---

## Pipeline (Target End-State)

```
MemoryService (store abstraction)
      ↓
MemoryRetriever.retrieve(query, limit, token_budget)
      ↓
RankedMemory[]   ← explainable (score is not a black box)
      ↓
[budget trimming — deterministic]
      ↓
MemoryContext
      ↓
ContextEngine
      ↓
AIService
      ↓
Provider / Agent
```

---

## Constraints (Non-Negotiable)

| Do Not Do | Reason |
|-----------|--------|
| ❌ Touch Vision / CV / Camera / MediaPipe / YOLO | Vision stays optional & frozen |
| ❌ Change `_run_agent_loop` / Agent Loop contract | Bounded, tested, working (max 5 rounds) |
| ❌ Change `AIProvider` / `AIResponse` / Tool protocol | Stable since Phase 2 |
| ❌ Introduce LangGraph / CrewAI / smolagents / multi-agent | Abstraction debt; workflow is still simple |
| ❌ Require embedding / vector DB / LLM for ranking v1 | Ranking v1 is deterministic & offline |
| ❌ Bind the contract to Qwen / OpenAI / any specific LLM | Provider-agnostic by design |
| ❌ Redesign the whole memory database | Reuse `MemoryManager` + `MemoryService` as-is |
| ❌ Add autonomous behavior | Context ≠ agency; keep scope minimal |

The contract must be **storage-agnostic** and **model-agnostic**.

---

## 1. MemoryRetriever Interface

New types live in a new module `aether/ai/memory.py` (not `aether/memory/`, to keep
the AI layer's contract separate from storage).

```python
class MemoryRetriever(Protocol):
    """Retrieve and rank memory for the AI context layer.

    Storage-agnostic: the caller only sees RankedMemory[] / MemoryContext.
    Implementations may wrap MemoryService / MemoryManager / a future vector store.
    """

    def retrieve(
        self,
        query: str = "",
        limit: int = 5,
        token_budget: int = 1500,      # approx characters budget
        memory_types: Optional[List[str]] = None,
    ) -> List[RankedMemory]:
        """Return memory records ranked by relevance to ``query``.

        - ``query == ""`` → recency-ranked recent memory.
        - Never raises: emits a warning + returns [] on source failure.
        """
        ...

    def remember(
        self,
        key: str,
        value: Any,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        memory_type: str = "semantic",
    ) -> Optional[str]:
        """Explicitly store a memory record. Returns record id or None."""
        ...

    def forget(self, memory_id_or_key: str) -> int:
        """Explicitly delete memory. Returns number of records removed."""
        ...

    def recall(self, memory_id_or_key: str) -> Optional[Dict[str, Any]]:
        """Explicit, deterministic lookup of a single record."""
        ...
```

### Design decisions

| Decision | Rationale |
|----------|-----------|
| `retrieve(query, limit, token_budget)` | Matches the user's locked signature; budget lives at the call site |
| `remember`/`forget`/`recall` are explicit | User must control what is stored; nothing auto-remembered in v1 |
| `retrieve` never raises | Context building must degrade gracefully (same rule as Phase 3.1) |
| Returns `List[RankedMemory]` | Caller owns final budget trimming; retriever owns ranking |
| `memory_types` filter | Lets System/Workspace/Memory domains request only relevant slices |

---

## 2. RankedMemory Model

```python
@dataclass(frozen=True)
class RankedMemory:
    memory: Dict[str, Any]          # record view (id, key, value, context, ...)
    score: float                    # final blended score (explainable)
    relevance_score: float          # text-match contribution (0..1)
    recency_score: float            #  0..1 (newest = 1.0)
    importance_score: float         #  0..1 (from metadata['importance'], default 0.5)
    type_weight: float              # per memory_type bias (table below)
    memory_type: str                # "semantic" | "episodic" | "spatial" | "working"
```

### Why expose sub-scores?

**`score` must never be a black box.** Every selected memory must be explainable:
*why* was this chosen? Exposing `relevance/recency/importance/type` sub-scores makes
rankings testable and auditable. Degradation is diagnosable ("it scored because it's
recent, not because it matches").

---

## 3. Ranking v1 (Deterministic)

No embeddings, no LLM scoring. Pure arithmetic over records returned by the source.

```text
final_score = relevance_score + recency_score + importance_score + type_weight
```

### 3.1 relevance_score (0..1)

- With a non-empty query: from best available text signal from the source:
  - FTS5 match (via `MemoryService.search(query)`) → baseline 1.0 for direct hits,
    scaled down by rank (first hit highest).
  - Substring overlap on key/title/content when only list access is available.
  - No match → 0.0.
- Empty query → treated as 0.0 (recency takes over).

### 3.2 recency_score (0..1)

```text
recency_score = 1.0 / (1.0 + age_days)
```
- `age_days` from `updated_at` (or `created_at` fallback).
- Newest record → ~1.0; a year-old record → ~0.27. No hard cutoff (recently-updated
  facts stay findable).

### 3.3 importance_score (0..1)

```text
importance = metadata.get("importance", 0.5)   # stored on the record
importance_score = min(1.0, max(0.0, float(importance)))
```

### 3.4 type_weight (constant bias)

| memory_type | weight |
|-------------|--------|
| `semantic`  | 0.2  |
| `episodic`  | 0.15 |
| `working`   | 0.1  |
| `spatial`   | 0.05 |

Rationale: semantic facts are most useful for answering conversational questions;
spatial records are least useful in a text prompt today (no CV integration active).
Weights are flat constants in v1 — no tuning until real usage data exists.

### 3.5 Determinism guarantee

- All inputs are deterministic for a fixed record set + fixed time.
- Ties are broken by `updated_at DESC` then `id` (stable).
- The same query at the same "now" always yields the same ordering.

---

## 4. Prompt Budget Policy

### Contract

```python
@dataclass(frozen=True)
class MemoryContext:                 # drives the [Memory] block in the prompt
    relevant: List[Dict[str, Any]]  # already budget-trimmed record views
    stats: Dict[str, int]           # objects / fact_keys / total_facts
    budget: MemoryBudget             # what was applied
    skipped_due_to_budget: int       # how many ranked items were trimmed away


@dataclass(frozen=True)
class MemoryBudget:
    max_items: int            # default 5
    max_chars: int            # default ~1500 (≈ ≤ ~400 tokens)
```

### Trimming algorithm (deterministic)

1. Take ranked list from `retrieve()`.
2. Keep the top `max_items` by score (already ordered).
3. Greedily append records in score order while cumulative serialized chars
   `<= max_chars`; stop as soon as the next record would overflow.
   - This is a **first-fit, score-ordered** cut — never random, never arbitrary.
4. `skipped_due_to_budget = len(ranked) - len(kept)`.

### Defaults

- `max_items = 5`, `max_chars = 1500` (≈ ~400 tokens) — matches Phase 3.1's
  `context.max_memory: 5`, keeps the total prompt comfortably under the ~2000-token
  budget already tested in Phase 3.1.
- Budget values are configurable via `config/ai.yaml` (`context.max_memory`,
  plus new `context.max_memory_chars`).

---

## 5. Remember / Forget / Recall — Explicit User Control

| Method | Behavior | Notes |
|--------|----------|-------|
| `remember(key, value, metadata, importance, memory_type)` | Stores one record via the source | Returns record id; **never implicit/auto** in v1 |
| `forget(id_or_key)` | Deletes by id or key | Returns count removed (0 if missing) — critical for user control |
| `recall(id_or_key)` | Single explicit lookup | Deterministic, not rank-based |

### Semantics

- **Nothing is auto-remembered.** Phase 3.2 only defines the *capability* for the
  user/AI to explicitly store and remove memory. (Episodic auto-logging is deferred
  to a later phase.)
- `forget` is first-class: a personal assistant must be able to un-remember.
- All three delegate to the injected source (MemoryService), with the same
  graceful no-crash rule: a source failure returns `None`/`0` and logs.

---

## 6. Integration Points

| Component | Change (at Implementation time) |
|-----------|--------------------------------|
| `aether/ai/memory.py` (new) | `MemoryRetriever` protocol, `RankedMemory`, `MemoryContext`, `MemoryBudget`, `MemoryContextBudget` helper, `DefaultMemoryRetriever` |
| `ContextEngine` (`aether/ai/context.py`) | In `_build_memory`, replace ad-hoc `_gather_memory_records` with a call to the injected retriever: `retrieve(query, limit, budget)` → trim → `MemoryContext` |
| `ContextEngine.__init__` | Accept `memory_retriever: Optional[MemoryRetriever]`; when absent, keep current behavior (backward compatible) |
| `AIService` | Pass `memory_types`/budget through; **no Agent Loop changes** |
| `AIPlugin` | Construct `DefaultMemoryRetriever(memory_service)` and inject into `ContextEngine` |
| `config/ai.yaml` | Add `context.max_memory_chars` (default 1500) |
| `MemoryService` | **No change.** It already provides `search/recall/recent/stats`; the retriever wraps it |

### Invariant preservation (unchanged from Phase 3.1)

- Vision = optional (frozen)
- CV = untouched
- AI = independent (Provider-agnostic)
- `_run_agent_loop` untouched

---

## 7. Error / Degradation Behavior

| Scenario | Behavior |
|----------|----------|
| Source (`MemoryService`) missing | `retrieve` returns `[]`; `MemoryContext.relevant=[]`, `stats={}`; no crash |
| Source raises | `Exception` caught, warning logged, `[]` returned |
| Query yields no matches | Falls back to recency-ranked recent memory (still useful) |
| Budget smaller than one record | Keep nothing after that record; `skipped_due_to_budget` reflects it |
| `forget` on missing record | Returns 0, no error |
| `remember` with empty key | Returns `None`, warning logged |
| Recency/age data missing | `age_days` treated as 0 → newest score |

All degradation is **deterministic and observable** — the same failure always yields
the same fallback.

---

## 8. Test Strategy

### 8.1 Unit (`tests/test_memory_retriever.py` new)

| Test | Assertion |
|------|-----------|
| `retrieve_empty_query_returns_recent` | Empty query ⇒ recency-ordered results |
| `retrieve_nonempty_query_ranks_by_relevance` | Match-bearing records score above recency-only |
| `score_not_black_box` | Each `RankedMemory` exposes all four sub-scores |
| `recency_prefers_newer` | Two same-relevance records: newer one ranks first |
| `importance_raises_score` | Higher `metadata['importance']` ⇒ higher total |
| `type_weight_matrix` | `semantic` > `episodic` > `working` > `spatial` for equal inputs |
| `budget_trims_deterministically` | Adding one oversized record results in a stable subset |
| `budget_respects_max_items` | Never more than `max_items` returned |
| `budget_respects_max_chars` | Cumulative serialized length ≤ `max_chars` |
| `skipped_due_to_budget_reported` | Trims are counted |
| `deterministic_ties` | Same input ⇒ same ordering |
| `source_missing_degrades_gracefully` | No source ⇒ `[]` + empty context, no raise |
| `source_raising_degrades_gracefully` | Raising source ⇒ `[]`, warning logged |
| `remember_forget_recall_roundtrip` | store → recall → forget → recall None |
| `forget_missing_returns_zero` | No record ⇒ 0 |

### 8.2 Integration (`tests/test_memory_retriever_integration.py` new)

| Test | Assertion |
|------|-----------|
| `context_engine_uses_retriever` | Injected retriever feeds `MemoryContext` |
| `new_fact_appears_in_next_turn` | remember + chat ⇒ fact in next `result.context.memory.relevant` |
| `forget_hides_memory` | forget ⇒ facts no longer surface |
| `vision_freeze_invariant` | Full build with `OverlayModel=None`; no CV imports in `aether/ai/**` |

### 8.3 Regression

- Full suite must stay **≥ 820 passing** (Phase 3.1 baseline).
- Existing `tests/test_context_engine.py` and `tests/test_ai_context_integration.py`
  must pass unchanged (backward compatibility of `ContextEngine.build`).

---

## 9. Acceptance Criteria

1. **Contract-first discipline** — this plan is reviewed and approved before any
   source code is written.
2. **Explainable ranking** — every `RankedMemory` exposes `relevance/recency/
   importance/type` sub-scores; no black-box `score`.
3. **Deterministic budget** — `MemoryContext` respects `max_items` + `max_chars`
   via a stable first-fit cut; trimming is never random.
4. **Explicit user control** — `remember`/`forget`/`recall` documented and testable;
   nothing auto-remembered in v1.
5. **Storage & model agnostic** — contract has zero dependence on SQLite specifics,
   FTS5, embeddings, or any LLM; providers/Qwen3 untouched.
6. **No regressions** — full suite ≥ 820 passing; Phase 3.1 tests unchanged.
7. **Vision/CV freeze** — `aether/ai/**` has no CV-stack imports; `OverlayModel=None`
   still yields a complete context.
8. **Zero Agent Loop changes** — `_run_agent_loop` untouched.

---

## 10. Files Touched (at Implementation time — NOT now)

| File | Change |
|------|--------|
| `aether/ai/memory.py` (new) | `MemoryRetriever` + `RankedMemory` + budget types + `DefaultMemoryRetriever` |
| `aether/ai/context.py` | `_build_memory` uses injected retriever; `MemoryContext` gains budget fields |
| `aether/ai/service.py` | Thread budget params through; no Agent Loop change |
| `aether/plugins/ai_plugin.py` | Build + inject `DefaultMemoryRetriever` |
| `config/ai.yaml` | Add `context.max_memory_chars: 1500` |
| `tests/test_memory_retriever.py` | New (unit) |
| `tests/test_memory_retriever_integration.py` | New (integration) |

---

## Rollout (after approval)

1. Implement `aether/ai/memory.py` (types + `DefaultMemoryRetriever`).
2. Wire `ContextEngine._build_memory` to the retriever (backward-compatible).
3. Wire `AIPlugin` to inject the retriever; add `config/ai.yaml` budget key.
4. Add unit + integration tests.
5. Run full suite — verify ≥ 820 pass, Vision freeze holds.
6. Commit: `feat: Phase 3.2 Memory Retriever`
7. Tag: `v1.0.0-memory-contract-stable`

---

## Out of Scope (Future Phases)

- Phase 3.3: Intent / Reasoning (explicit reasoning steps, CoT)
- Phase 3.4: Capability / Permissions (tool-scoped safety)
- Phase 3.5: Assistant UI
- Later: embedding / vector ranking (ranking v2+) — only after v1 usage data exists
- Later: episodic auto-logging ("what happened when") — deferred, not in v1
- Later: real LLM (Qwen3/OpenAI) optimization — only after this contract is stable
