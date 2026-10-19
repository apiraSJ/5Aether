# Mark 1 Review Audit — `D:\3CS\5Aether` (2026-10-19)

> READ-ONLY audit (Step 0 of Aether Mark 1). No product code was modified, no schema changes, no dependency changes, no files created outside this report. Findings below are verified against the working tree at commit `da3419c` (`main` == `origin/main`).

## 0. Scope & boundaries

Per locked Mark 1 plan:

1. Inspect real structure, service/plugin lifecycle, repository, event bus, and current test suite.
2. Record reusable assets, required additions, touch points, and frozen zones.
3. Assess risks before creating `data/tasks.db` and Mark 1 migrations.
4. Do not start Phase 1 until this report exists and findings support the plan.
5. No external AI calls; do not touch the 11 untracked legacy tests; stage nothing.

Git state at audit time: `da3419c`, clean except exactly the 11 pre-existing untracked legacy test files (`test_integration_phase3a5`, `test_layout_manager`, `test_layout_persistence`, `test_notification_manager`, `test_panel_abstraction`, `test_perf_metrics`, `test_real_panels`, `test_runtime_validation`, `test_theme_manager`, `test_ui_commands`, `test_workspace_autosave`). Nothing staged.

## 1. Verification results (evidence)

| # | Claim | Verified | Evidence |
|---|---|---|---|
| 1 | Test baseline intact | ✅ | `pytest -q` → **1091 passed** in 55.86s (62 test files) |
| 2 | `ITaskRepository` has zero implementations | ✅ | Only refs in `aether/core/interfaces/i_memory_repository.py:75` + `__init__.py` export; no implementation anywhere |
| 3 | `TASK_*` events defined but never published/consumed | ✅ | Only occurrences in `aether/core/event_type.py:182-185,253-256` |
| 4 | `domain/task.py` Task is vestigial, no schedule fields | ✅ | Execution semantics only (`PENDING→RUNNING→…`); no `due_date`/`start_at`/`end_at`/`all_day` |
| 5 | No date/time parsing anywhere | ✅ | Zero hits for `strptime`/`dateutil`/`relativedelta`/Thai+EN NL date keywords across `aether/` |
| 6 | No web framework in code | ✅ | Zero imports of `fastapi`/`uvicorn`/`flask`/`starlette`/`http.server` in any `.py` |
| 7 | No auth/tokens/users | ✅ | Only hits are `ai/providers/openai.py` API-key plumbing (env `OPENAI_API_KEY`, default provider is `echo`) |
| 8 | FastAPI available but undeclared | ✅ | venv: fastapi 0.139.2, uvicorn 0.51.0, pydantic 2.13.4, Python 3.12.9; absent from `requirements.txt`/`pyproject.toml` |
| 9 | Lifecycle/DI structure | ✅ | `aether/core/service_container.py`, `plugin_loader.py`, `application.py` present; plugin pattern proven by `memory_plugin.py`/`baseline_plugin.py`/`voice_input_plugin.py` |
| 10 | SQLite precedent | ✅ | `aether/memory/schema.py` (WAL, FK ON, FTS5, `metadata.schema_version` row), `sqlite_repository.py` (669 ln, only raw sqlite3 code); no migration/upgrade path exists |

## 2. Reusable assets (extend — do not tear down)

| Asset | Why it fits Mark 1 |
|---|---|
| `event_type.py` `TASK_CREATED/UPDATED/COMPLETED/CANCELLED` | Defined, unused — Mark 1 becomes their first publisher |
| `ITaskRepository` (interface) | Untouched; Mark 1 adds a **new** `IScheduleRepository` typed to the new model instead of forcing the vestigial `Task` |
| `memory/schema.py` + `sqlite_repository.py` | Schema style (WAL/FK/`executescript`) and connection handling to mirror for `tasks.db` |
| `plugins/memory_plugin.py` | End-to-end command → repository → event wiring reference (WorkSession CRUD) |
| `plugins/baseline_plugin.py` | CommandInfo catalog + handler registration reference |
| `voice/intent_parser.py` + `plugins/voice_input_plugin.py` | Deterministic Thai/EN rule-based parsing pattern — direct template for temporal engine |
| `ServiceContainer` + `PluginLoader` (YAML specs) | DI/lifecycle for `task_plugin` registration in `config/task.yaml` |
| `.gitignore:43-45` (`*.db`, `*.db-wal`, `*.db-shm`) | `data/tasks.db` (+WAL/SHM) automatically never tracked |

## 3. Gaps (all Mark 1 work — nothing exists)

- **Data model**: no schedule-bearing task/event entity; vestigial `domain/task.py` stays frozen (contract tests depend on it).
- **Persistence**: no `tasks.db`, no migration mechanism anywhere in the repo (the `schema_version` metadata row is write-only, never read).
- **Temporal engine**: zero date/time parsing (Thai or English, absolute or relative).
- **Chat extraction**: no long-paste parser, no evidence/confidence model, no review queue.
- **Web/backend/auth**: no framework declared, no routes, no users, no tokens, no HTML/JS/CSS assets; UI is desktop-only PySide6.
- **Metrics**: no labeled corpus, no extraction/precision harness.

## 4. Touch points (Mark 1 will legitimately modify)

| File | Change (at Phase) | Risk |
|---|---|---|
| `aether/core/event_type.py` | None expected — existing `TASK_*` reused as-is | None |
| `config/default.yaml` / `config/vision.yaml` | Register `task_plugin` + `task:` section (Phase 2) | Low — additive YAML keys, boot-tested |
| `requirements.txt` / `pyproject.toml` | Declare `fastapi`/`uvicorn` under `[server]` extra (Phase 7) | Low — additive, lazy usage |
| `aether/core/interfaces/` | Add new `i_schedule_repository.py` (Phase 1) | None — new file |
| `.gitignore` | None needed — `*.db*` already covered | None |

## 5. Frozen zones (do not touch)

- 11 untracked legacy tests (left untracked, unmodified).
- `aether/domain/task.py` + `ITaskRepository` — left exactly as-is; Mark 1 does not repurpose them.
- `aether/memory/*` schema, repository, `data/memory.db` — Memory Core untouched.
- `aether/ui/**`, vision/gesture/interaction stacks — out of Mark 1 scope.
- Existing 1091 tests — must remain green unmodified.
- No external AI egress (AI provider stays `echo`; no private text leaves the machine).

## 6. Risk assessment before `data/tasks.db`

| Risk | Assessment | Mitigation (in plan) |
|---|---|---|
| DB file leaks into git | **Closed** — `.gitignore:43-45` covers `*.db`/`*.db-wal`/`*.db-shm`; verified via `git check-ignore` | None needed; assert in Phase 1 test |
| Collision with `memory.db` | None — separate file, separate connection, `data/tasks.db` | Own `PRAGMA user_version` migrations, applied at startup |
| Migration drift (no precedent in repo) | **Real** — repo has no migration runner to copy | Hand-rolled `migrations.py`: append-only ordered list, `user_version` gate, never edit an applied migration |
| Concurrent writes (plugin + future server) | Both write paths go through the same repository; WAL allows concurrent readers | Single repository instance per process; service-layer conflict detection (updated_at compare) + history rows |
| Wiping `tasks.db` on schema change during dev | Possible pre-ship | Version-gated migrations + Phase 8 persistence/restart tests |
| Kind-field misuse (task vs event columns) | Single-table design invites null-field drift | Service-layer validation per `kind` (task: `due_date` optional; event: `start_at`/`end_at` or `all_day`) — enforced in Phase 1 tests |

## 7. Verdict

All Phase 0 checklist items complete (lifecycle/services ✅ · SQLite ✅ · task/temporal ✅ · web/API/privacy ✅). Findings **support the locked plan**:

- FastAPI+uvicorn: available (0.139.2/0.51.0) but undeclared — declare at Phase 7 as planned. ⚠️ Note: installed-in-venv ≠ in-use; nothing imports it today, so integration starts from zero, no legacy web code to reconcile.
- `data/tasks.db`: zero collision risk (separate file, gitignored); migration mechanism must be built from scratch (no in-repo precedent) — plan already assumes this.
- Desktop plugin + server entry: supported by proven plugin lifecycle; business logic lives in services shared by both entry points.
- Single `items` table: feasible; requires service-layer per-kind field rules (added to Phase 1 test scope).

**Phase 0 status: COMPLETE. Phase 1 (data model + SQLite + migrations) is unblocked pending explicit go.**
