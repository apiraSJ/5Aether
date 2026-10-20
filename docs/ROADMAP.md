# Aether Mark-1 Roadmap

## Current Status (commit `a148439`)

**Backend v1.0.0** — Architecture Stable (tagged `backend-v1.0.0`)

- Core runtime: Boot/Tick/Shutdown, EventBus, CommandBus, Plugin System
- Vision pipeline: Camera, YOLO, MediaPipe, FrameBroker, AdaptiveScheduler
- UI: UIShell with camera, panels, workspace, lifecycle (show/hide/toggle)
- CLI: Event-driven with IntentResolver, CommandRegistry, tab-completion
- **Schedule Engine (Track A):** Task/Calendar domain, SQLite `tasks.db`, import/export, validation — 1,349 tests passing

---

## Track A — Schedule Engine (Python)

**Goal:** Deterministic Task & Calendar engine with validation, import/export, and review queue.

### Phase 1 — Schedule Domain ✅

- [x] Data model: `TaskItem` (task + event), `Evidence`, `HistoryEntry`, `ReviewEntry`, `ImportBatch`
- [x] SQLite schema with WAL, FK, `user_version` migrations
- [x] `IScheduleRepository` + `SqliteScheduleRepository`
- [x] `ScheduleService` with validated CRUD, optimistic concurrency, audit history
- [x] 110 tests

**Commit:** `998eff9`

### Phase 2 — Task Plugin & Calendar ✅

- [x] `task_plugin` (6 commands: create, list, complete, cancel, update, calendar)
- [x] Post-commit `TASK_CREATED/UPDATED/COMPLETED/CANCELLED` events
- [x] Calendar queries (due_date vs overlap rules, no midnight spill)
- [x] Config wiring (`config/task.yaml`, `config/default.yaml`)
- [x] 80 tests

**Commit:** `80baa78`

### Phase 3 — JSON Import/Export ✅

- [x] Canonical JSON adapter (stable hash, whitespace/order insensitive)
- [x] File-level dedupe (content_hash) + per-item identical-content dedupe
- [x] Conflict policies: `review` (default, parks in review_queue), `update` (writes IMPORTED history), `skip`
- [x] Atomic batch transaction (items + review rows + import_batches row)
- [x] Offset-aware datetime normalization; date-only preserved (no midnight)
- [x] 53 tests

**Commit:** `296c3c0`

### R1 — Chronology Validation (mixed-offset) ✅

- [x] Adapter compares instants (offset-aware), not raw strings
- [x] Service mirrors same normalization-then-compare semantics
- [x] Fixes false-reject of equal instants across offsets (e.g., 14:00+09:00 vs 12:00+07:00)
- [x] 9 new regression tests

**Commit:** `20faedc`

### R6 — Reject date-only timestamps for timed tasks ✅

- [x] Service rejects bare `YYYY-MM-DD` in `start_at`/`end_at` when `all_day=False`
- [x] `all_day=True` still accepts date-only (no time inflation)
- [x] 5 regression tests

**Commit:** `a148439`

### Phase 4 — Temporal Extraction (Draft) ⏳

**Spec:** `docs/PHASE4_SPEC.md` (Draft, not approved for implementation)

- [ ] Deterministic chat/long-paste extraction → `TaskItem` candidates
- [ ] Low-confidence/ambiguous items → `internal_status=NEEDS_CONFIRMATION` + `review_queue`
- [ ] Time-only (`"14:00"`) never auto-bound to a date; routed to review
- [ ] Unsupported timezone names preserved in payload, not silently converted
- [ ] Batch atomicity: one extraction text = one transaction
- [ ] No external AI; deterministic rules only

---

## Track B — Web Application (Planned)

**Goal:** Web Task & Calendar Assistant (HTML/CSS/JS + PHP) using Track A engine via API.

### MVP Scope

- [ ] Web UI: Task list, Task creation, Calendar/Event view
- [ ] Responsive: desktop + mobile browsers
- [ ] PHP backend calling Track A Python services via HTTP API
- [ ] Shared SQLite `data/tasks.db` (read/write via Python service)
- [ ] No schema migration; Track A remains single writer
- [ ] Auth: local-only for MVP (no multi-user production)

### Architecture (high-level)

```
Browser (HTML/CSS/JS)
       │
       ▼
PHP Web Backend
       │
       ▼ (HTTP API)
Python FastAPI (Track A services)
       │
       ▼
ScheduleService → SqliteScheduleRepository → data/tasks.db
```

### Out of Scope for MVP

- Cloud deployment / public internet exposure
- Native Android/iOS apps
- Multi-user production auth
- Rewriting Task/Calendar engine in PHP
- Schema changes or DB migration without approved plan
- Memory Core rewrite
- External AI / LLM providers for extraction
- Phase 4 implementation before spec approval

---

## UI Lifecycle — Desktop UX Foundation (unchanged)

**Goal:** Aether behaves as a normal desktop application with opt-in background mode.

### Lifecycle Semantics (locked)

```
Background ≠ Shutdown
Hide ≠ Shutdown
Quit = real graceful shutdown
```

### Execution Order

```
UI-0 → UI-1 → UI-3 → UI-4 → UI-2 → UI-5 → UI-6
```

### UI-0: Startup Visibility ✅
**Commit:** `d73b82a` | Tests: 909 → 909 (18 UI-0 tests added)

### UI-1: Runtime Control ✅
**Commit:** `dfd5d36` | Tests: 909 → 921 (12 UI-1 tests added)

### UI-2: Global Hotkey 🔄 (planned)
**Plan:** `docs/UI-2-plan.md`

Scope (locked):
- [ ] Ctrl+Alt+Space via Win32 `RegisterHotKey` (ctypes)
- [ ] `GUIPlugin._parse_hotkey()`, `_register_hotkey()`, `_poll_hotkey()`, `_unregister_hotkey()`
- [ ] Calls `GUIPlugin.toggle_ui()` → `UIShell.toggle()`
- [ ] 12 tests (parser, registration, dispatch)

NOT in scope: system tray, window −/×, Alt+F4, persistence, shutdown, UI redesign, panel changes.

### UI-3: Window Controls (planned)
- [ ] Custom `−` (hide) and `×` (quit) buttons
- [ ] Frameless `Qt.Tool` window
- [ ] `−` → `GUIPlugin.hide_ui()` → `UIShell.hide()`
- [ ] `×` → `system.shutdown` → `app.request_shutdown()`

### UI-4: System Tray (planned)
- [ ] QSystemTrayIcon with context menu
- [ ] Show / Hide / Quit actions
- [ ] Tray → Hide → `GUIPlugin.hide_ui()`

### UI-5: Persistence (planned)
- [ ] `data/ui_state.json` (git-ignored)
- [ ] Save/restore window position, visibility
- [ ] Auto-save on shutdown

### UI-6: Polish & Edge Cases (planned)
- [ ] Alt+F4 → `system.shutdown` (not hide)
- [ ] Taskbar behavior
- [ ] Multi-monitor support
- [ ] Focus restore after show()

---

## Design Principles (Post-v1)

1. **Every commit adds user-facing capability** — no more infrastructure-only changes
2. **Backend v1 is frozen** — fix only bugs or security issues
3. **Two-track delivery** — Track A (Schedule Engine) stabilizes first; Track B (Web) consumes it
4. **Test everything** — 1,349+ tests, run before every commit
5. **No external AI egress** — provider stays `echo`; deterministic rules only