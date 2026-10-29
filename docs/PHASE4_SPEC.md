# Aether Mark 1 — Phase 4 Spec (DRAFT — for approval, no code)

> Status: **DRAFT**. Not locked. No Phase 4 implementation until this document is
> approved. Scope is the deterministic temporal-extraction engine that turns
> free text (chat paste) into schedule items.

## 0. Scope lock

| Item | Requirement |
|---|---|
| Input | Free text or pasted chat text |
| Extraction | Deterministic rules only (Thai + EN), no external AI |
| Output | `TaskItem` candidates + `Evidence` + confidence |
| Ambiguity | `InternalStatus.NEEDS_CONFIRMATION` + `review_queue` |
| Writes | Only through `ScheduleService` (never `repository.save()` directly) |
| External AI | None (provider stays `echo`) |
| Out of scope | Web/server (Phase 7), UI panels, Memory Core, `aether/domain/task.py`, schema changes |

### 0.1 Verified prerequisites (evidence)

These were checked against the working tree; the spec depends on them.

1. **Single shared connection.** `SqliteScheduleRepository` holds one `sqlite3.Connection`
   (`repository.py:47`), `isolation_level=None` (manual control), guarded by one `RLock`.
   Every method uses `self._conn` under `self._lock` — service and repository writes
   share the same connection (verified: stable `id(self._conn)`).
2. **Re-entrant transaction = one real BEGIN/COMMIT.** `transaction()`
   (`repository.py:82-104`) issues `BEGIN IMMEDIATE` only at depth 0; a nested call
   joins the open transaction (`_txn_depth += 1`, no new BEGIN). Any exception rolls
   back the whole thing. Verified: depth 1 → nested depth 2 → back to 1, single commit.
3. **`ScheduleService.update()` / `create()` already do multi-step writes inside one
   `repo.transaction()`** (item write + history append) — same pattern Phase 4 reuses.
4. **`service.delete()`** writes `DELETED` history first, then deletes the item;
   history survives (no FK). Verified: history after delete = `[deleted, created]`,
   item gone. Evidence + review rows cascade away.
5. **Review uniqueness.** `idx_review_one_pending` unique partial index on
   `review_queue(item_id) WHERE state='pending'` — at most one PENDING row per item.
6. **`internal_status`** is a column on `items` (`schema.py:28`), default `'confirmed'`,
   CHECK in (`confirmed`,`needs_confirmation`). No code currently sets it — Phase 4 is
   its first producer.

## 1. R2 — Review lifecycle

### 1.1 Transaction model (locked semantics)

All review-producing / review-resolving operations are wrapped in a **single
top-level** `repo.transaction()`. Nested `repo.transaction()` calls (e.g. inside
`service.create()`/`update()`/`delete()`) **join** the outer transaction — there is no
separate connection and no second BEGIN. Therefore item + review + history are
all-or-nothing by construction, not by convention.

> Acceptance test required: inject a failure at each internal step and assert **zero**
> residual state (no item, no review row, no history row) — mirroring the existing
> `TestTransactionAtomicity` monkeypatch pattern (`test_task_service.py:372`).

### 1.2 Create (uncertain extraction)

```
with repo.transaction():                       # one BEGIN
    item = service.create(..., internal_status=NEEDS_CONFIRMATION)
    repo.enqueue_review(ReviewEntry(
        item_id=item.id,
        reason=<"ambiguous time: missing date" | "low confidence" | ...>,
        payload={<raw fields, excerpt, rule id>},
        confidence=<rule score>,
        state=ReviewState.PENDING,
    ))
    service.attach_evidence(item.id, source="chat", source_ref=..., excerpt=..., confidence=...)
# single COMMIT
```

### 1.3 Resolution — decision matrix

| Decision | Item change | History | Review |
|---|---|---|---|
| **confirm** | `update(internal_status=CONFIRMED)` (fields unchanged) | append `REVIEWED` (note="confirmed") | `resolve_review(CONFIRMED)` |
| **edit** | `update(<corrected fields>, internal_status=CONFIRMED)` | `UPDATED` (before/after) **and** `REVIEWED` (note="edited") | `resolve_review(EDITED)` |
| **reject** | `service.delete(item_id)` (chosen over `cancel`) | `DELETED` survives (audit not lost) | `resolve_review(REJECTED)` |

**Delete vs cancel (decision):** reject uses `service.delete()`.
Rationale: a rejected *extraction* was never a real user item; `cancel` would leave a
`cancelled` item in lists that the user never wanted. `delete()` preserves audit via
the FK-less `item_history`, and review/evidence rows cascade — the review row itself
is resolved to `REJECTED` (not cascaded) by resolving **before** delete ordering or
after within the same transaction; the spec requires `resolve_review(REJECTED)` to be
recorded and the row state to end `rejected`, not vanish.

> Implementation note for the later coding phase: to keep the `REJECTED` row visible,
> resolve the review row **before** `service.delete()` (the delete cascades review rows
> for that item). Exact ordering is an implementation detail that MUST be covered by a
> test asserting the review ends in `REJECTED` and the item is gone.

All three rows write inside **one** `repo.transaction()`.

### 1.4 Invariant (enforced + tested)

> **RI-1** At any committed state, an item with `internal_status='needs_confirmation'`
> has exactly one PENDING review row, and every PENDING review row references an item
> with `internal_status='needs_confirmation'`.
>
> Transient states *inside* an open transaction (before COMMIT) are exempt — the
> invariant is only required at commit boundaries.

- Scope of `needs_confirmation`: **only** the extraction/review pipeline creates it.
  Import (`on_conflict`) does NOT set it (import conflict review rows carry
  `internal_status='confirmed'`); see §1.6.
- Read-side helper `ScheduleService.list_reviews()` / `repo.list_reviews(PENDING)`
  plus an assertion test that walks all PENDING rows and checks item status.

### 1.5 Failure semantics

- Any exception inside the wrapping transaction → full ROLLBACK (item + review +
  history). No half-resolved item, no orphan PENDING row.
- `resolve_review` returns `False` when the row is not PENDING (already resolved /
  race) → the wrapper treats this as a conflict and **rolls back**, never silently
  succeeds.

### 1.6 Existing import review rows (reconciliation)

Phase 3 import conflict rows are created with `state=PENDING` on items whose
`internal_status` stays `confirmed`. This is a **separate review kind**. The spec adds
a `payload["kind"]` discriminator (`"extraction"` vs `"import_conflict"`) so RI-1 is
scoped to `kind="extraction"` rows only. No Phase 3 behavior changes.

## 2. R3 — Ambiguous time (`"14:00"`, `"บ่ายโมง"`, `"เย็นนี้"`)

| Rule | Detail |
|---|---|
| No auto-day | Time-only text **never** binds to today, tomorrow, or any inferred date. `"14:00"` is incomplete data, not "today 14:00". |
| No fake field | The engine MUST NOT construct any `start_at`/`end_at` while the date is missing. Candidate carries only the raw time string. |
| Route | Create item `internal_status=NEEDS_CONFIRMATION`, review `reason="ambiguous time: missing date"`, `kind="extraction"`, payload holds `{raw_time, excerpt, rule_id}`. |
| Evidence | Original text stored as `Evidence(source="chat", excerpt=..., confidence=<rule score>)`. |
| Resolution | Only after the user supplies a date does the engine build a normal `start_at` and `service.update(...)` → CONFIRMED; review resolved EDITED. |

> Required tests: (a) extraction with no date produces `needs_confirmation` + PENDING
> review and **no** item datetime fields; (b) freeze/patch the system date to two
> different days and assert the candidate is byte-identical (proves no "today" binding).

## 3. R4 — Timezone identity vs UTC offset (corrected wording)

The earlier draft said "preserve the original offset". Precise rules:

| Case | Rule |
|---|---|
| Explicit offset datetime, e.g. `2026-10-20T14:00:00+09:00` | Store the **instant with its offset** as the model already supports (`normalize_datetime` preserves aware values; verified). Never convert silently. |
| Named timezone not supported, e.g. `Asia/Tokyo` (not in `TZ_OFFSETS`) | Do **NOT** claim to understand it. Keep the **original name** in `review.payload`/evidence, mark `needs_confirmation`, ask the user. Do not equate `Asia/Tokyo` with a raw `+09:00`. |
| No offset AND relies on an unsupported tz | **Never guess** an offset to produce a supposedly-confirmed time. Route to review. |

- `TZ_OFFSETS` additions must keep the existing no-DST guarantee documented in
  `models.py:26-33`; adding a name is a separate, explicit change — not a silent fallback.
- Bangkok/UTC remain the only directly supported identities; an offset alone is not an identity.

## 4. Multi-item / batch atomicity (new)

When extraction finds **several items in one text**, define a text/batch boundary:

- One `repo.transaction()` per extraction **batch** (one input text) wrapping **all**
  candidate creates + review rows + evidence for that text.
- Any failure → the entire batch rolls back; no partial import of a single message.
- `ImportBatch` (existing table) is reused as the batch record: `source="extraction"`,
  `content_hash = sha256(canonical raw text)`, `stats={created, needs_confirmation, ...}`.
  A repeated identical text is deduped by `content_hash` (same mechanism as Phase 3).
- Per-item confidence is stored on evidence/review; the batch stores only counts.

> Required test: a 3-item text where the 2nd candidate fails domain validation →
> 0 items, 0 review rows, 0 batch row persisted.

## 5. API surface (names TBD at coding time, boundaries fixed)

- New module `aether/task/extraction.py`: pure functions `text -> List[Candidate]`
  (no DB access, fully unit-testable).
- `extraction` results are **persisted only** by a coordinator that calls
  `ScheduleService` inside one `repo.transaction()` (see §4).
- `ScheduleService` gains (proposed, approval only): `list_pending_reviews()`,
  `resolve_review(review_id, decision, *, corrected_fields=None, actor=...)` which
  internally performs the §1.3 matrix. Repository keeps `enqueue_review` /
  `list_reviews` / `resolve_review` as-is.
- CLI commands (proposed): `task.review.list`, `task.review.confirm <id>`,
  `task.review.edit <id> <fields...>`, `task.review.reject <id>`.

## 6. Acceptance criteria (Phase 4 done)

1. Deterministic tests for the R3 date-binding prohibition (two system dates → identical output).
2. R2 atomicity tests: failure injection at create / update / resolve / delete steps → zero residual state.
3. RI-1 invariant test over a mixed dataset (extraction PENDING rows only).
4. R4 tests: offset preserved; unsupported tz name preserved in payload + review, never guessed.
5. Batch atomicity test (§4) — partial failure writes nothing.
6. Full suite green; no schema change; Memory Core untouched; provider stays `echo`.
7. Diff limited to `aether/task/extraction.py` (new), `aether/task/service.py`,
   `aether/plugins/task_plugin.py`, config wiring, and tests.

## 7. Open questions for your decision

1. **Reject ordering** (§1.3): resolve review row *before* `delete()` (keeps REJECTED
   row, cascades evidence) — acceptable, or prefer `ON DELETE` change? (Default:
   resolve-before-delete, no schema change.)
2. Should a "confirm" with **no field change** still append a `REVIEWED` history row
   (audit of the decision) even though `UPDATED` would be empty? (Default: yes, a
   dedicated `REVIEWED` row.)
3. Batch record: reuse `ImportBatch` with `source="extraction"` (default) or add a
   distinct batch source table? (Default: reuse, additive.)
