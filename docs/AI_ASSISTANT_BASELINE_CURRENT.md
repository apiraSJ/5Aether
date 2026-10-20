# Aether AI Assistant Development — Current Baseline (2026-10-20)

> **This document records the current baseline** of the Aether repository at commit
> `a148439` (Oct 20, 2026), after Mark-1 Schedule Engine (Track A) Phases 1-3 + R1/R6
> are complete. It supersedes the historical baseline in `AI_ASSISTANT_BASELINE.md`.

## Baseline Metrics (Current)

- **State Statement**: 1,349 tests passing after Mark-1 Track A completion.
- **Pytest Command**: `.venv\Scripts\python -m pytest`
- **Python Version**: `Python 3.12.9`
- **Pytest Version**: `9.1.1`
- **Test Count**: `1,349`
- **Passing Count**: `1,349`
- **Failing Count**: `0`
- **Execution Time**: `~29 seconds`

---

## Current Status (Mark-1 Track A Complete)

### Test Status
- **Test Count**: `1,349`
- **Passing Count**: `1,349`
- **Failing Count**: `0`
- **Latest Commit**: `a148439` fix: R6 reject date-only timestamps for timed tasks

### Recent Commit History

```
a148439 fix: R6 reject date-only timestamps for timed tasks
20faedc fix: R1 chronology validation for mixed-offset datetimes
296c3c0 feat: Mark 1 Phase 3 - JSON import/export adapter
80baa78 feat: Mark 1 Phase 2 - task plugin (6 commands, calendar)
998eff9 feat: Mark 1 Phase 1 - schedule domain (items/evidence/history/review/batches)
```

---

## Mark-1 Track A — Schedule Engine (Complete)

### Phases Completed

| Phase | Scope | Commit | Tests |
|-------|-------|--------|-------|
| Phase 1 | Schedule domain (models, schema, migrations, repository, service) | `998eff9` | 110 |
| Phase 2 | Task plugin (6 commands, calendar queries, TASK_* events) | `80baa78` | 80 |
| Phase 3 | JSON import/export (canonical hash dedupe, conflict policies, atomic batch) | `296c3c0` | 53 |
| R1 | Chronology validation (mixed-offset instant comparison) | `20faedc` | 9 |
| R6 | Date-only rejection for timed tasks (no midnight inflation) | `a148439` | 5 |

### Components Added

| Component | Location | Purpose |
|-----------|----------|---------|
| Models | `aether/task/models.py` | TaskItem, Evidence, HistoryEntry, ReviewEntry, ImportBatch, enums, datetime utils |
| Schema | `aether/task/schema.py` | SQLite DDL (items, evidence, item_history, review_queue, import_batches) |
| Migrations | `aether/task/migrations.py` | Append-only user_version migrations |
| Repository | `aether/task/repository.py` | SqliteScheduleRepository (CRUD + evidence + history + review + batches) |
| Service | `aether/task/service.py` | ScheduleService (validated CRUD, optimistic concurrency, audit) |
| Calendar | `aether/task/calendar_query.py` | Pure day/week/month views, overlap detection |
| JSON Adapter | `aether/task/json_adapter.py` | Canonical import/export, dedupe, conflict policies |
| Plugin | `aether/plugins/task_plugin.py` | 8 CLI commands, TASK_* events, config wiring |

### Locked Data Model Invariants

- **Single table** `items` with `kind` (`task` | `event`)
- **Task:** `due_date` optional date-only; `all_day` forbidden
- **Event:** `start_at` required; `all_day=True` keeps date-only (no midnight); `due_date` forbidden
- **Date-only** (`YYYY-MM-DD`) never becomes midnight; only allowed with `all_day=True`
- **Offset-aware datetimes** preserved; naive gain item tz at single write boundary
- **Review queue** — unique pending row per item; `NEEDS_CONFIRMATION` + `PENDING` = uncertainty
- **Import batches** — canonical SHA-256 content hash for file-level dedupe
- **History** — append-only, survives deletion (CREATED, UPDATED, COMPLETED, CANCELLED, DELETED, IMPORTED, REVIEWED)

### Locked Validation Rules

- **R1 (Chronology):** Compare instants, not raw strings. Naive → item tz; aware preserved. Fixes false-reject/accept with mixed offsets.
- **R6 (Date-only):** Bare `YYYY-MM-DD` in `start_at`/`end_at` rejected when `all_day=False`.

---

## Mark-1 Track B — Web Application (Planned, Not Started)

### Status

- **Not implemented.** Architecture direction approved; API contract not designed.
- **Stack:** HTML/CSS/JS frontend + PHP backend → FastAPI (Python) → ScheduleService
- **Database:** Shared `data/tasks.db` (SQLite WAL); Python service remains sole writer
- **Auth:** Local-only for MVP (no multi-user)

### Planned Scope (MVP)

- Task list, creation, editing, completion via browser
- Calendar/Event view (day/week/month)
- Responsive: desktop + mobile browsers
- Review queue UI for extraction uncertainty + import conflicts

### Out of Scope for MVP

- Cloud deployment / public internet
- Native Android/iOS apps
- Multi-user production auth
- Rewriting engine in PHP
- Schema changes without approved plan
- External AI / LLM providers

---

## Git State (Current)

- **Branch**: `main`
- **HEAD Commit**: `a148439` (R6)
- **Working Tree**:
  - **Modified**: `tests/test_task_service.py` (1 noise hunk: `test_fresh_updated_at_passes` → `test_fresh_updated_at_pass`)
  - **Untracked**: `docs/PHASE4_SPEC.md` (Draft), 11 legacy test files

---

## Frozen Vision / Computer Vision Boundaries (Unchanged)

The following Computer Vision components remain frozen per original baseline:

1. **Camera Interface**:
   - `aether/phase_d/camera_plugin.py`
   - `aether/core/frame_broker.py`
2. **YOLO Bounding Box / Spatial Detections**:
   - `aether/phase_d/object_plugin.py`
3. **MediaPipe Hand Landmarking / Gesture Processing**:
   - `aether/phase_d/hand_plugin.py`
   - `aether/plugins/gesture_plugin.py`
4. **Virtual Cursor Input Adapter**:
   - `aether/phase_d/cursor_plugin.py`
   - `aether/core/virtual_cursor.py`
5. **Perception and Event Adapters**:
   - `aether/vision/` (all files)

---

## Phase 4 — Temporal Extraction (Draft Spec)

- **Spec:** `docs/PHASE4_SPEC.md` (Draft, not approved)
- **Scope:** Deterministic chat/long-paste extraction → TaskItem candidates
- **Key rules:** Time-only never auto-bound to date; unsupported timezone names preserved; batch atomicity; no external AI
- **Status:** Awaiting spec approval before implementation