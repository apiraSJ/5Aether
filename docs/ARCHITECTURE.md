# Aether Architecture — Backend v1.0.0

## Overview

Aether is a **command-driven operating system** with a unified interaction layer. All input sources (camera, keyboard, CLI, voice) flow through a single pipeline:

```
Input → EventBus → IntentResolver → CommandBus → Handler → ResultPipeline → Output
```

### UI Lifecycle Semantics (locked)

```
Background ≠ Shutdown
Hide ≠ Shutdown
Quit = real graceful shutdown
```

| Action | Result |
|--------|--------|
| Normal boot | UI visible, runtime active |
| `--background` | UI hidden, runtime active |
| Hide (button/tray/hotkey) | UI hidden, runtime active |
| Quit (system.shutdown) | Real graceful shutdown |

---

## Core Lifecycle

```text
Boot (Application.boot)
  │
  ├─ Load config (default.yaml)
  ├─ Create ServiceContainer
  ├─ --background? → override gui.start_visible = False
  ├─ Initialize plugins (order matters)
  ├─ Start camera thread
  └─ Start main loop
       │
       ▼
Tick (30 Hz)
  │
  ├─ CommandBus.update() → execute queued commands
  ├─ Services.update(dt) → domain logic
  ├─ GUIPlugin.update(dt)
  │     ├─ UIShell.update() → HUD render + processEvents
  │     └─ _poll_hotkey() → Ctrl+Alt+Space → toggle_ui()
  ├─ EventBus.flush() → deliver all queued events
  └─ AdaptiveScheduler + Profiler
       │
       ▼
Shutdown
  │
  ├─ Unregister global hotkey
  ├─ UIShell.shutdown() → save layout, hide window
  ├─ Signal all threads to stop
  ├─ Join threads (timeout 2s)
  └─ Release resources
```

---

## One-Way Data Flow

```
CameraPlugin ──▶ FrameBroker ──┬──▶ HandPerceptionPlugin ──▶ PerceptionResult
                                └──▶ ObjectSpatialPlugin  ──▶ PerceptionResult
                                                                 │
                                                                 ▼
                                                        VisionAdapterPlugin
                                                                 │
                                                                 ▼
                                                           EventBus (queued)
                                                                 │
                                                                 ▼
                                                      OverlayController
                                                                 │
                                                                 ▼
                                                         OverlayModel (state)
                                                                 │
                                                                 ▼
                                                      Widgets (stateless renderers)
```

**Key invariant:** Frame data never flows through the EventBus. Only perception results do.

---

## Service Container

All services are registered and resolved via DI:

```python
container.register("event_bus", EventBus())
container.register("command_bus", CommandBus(event_bus, result_pipeline))
container.register("frame_broker", FrameBroker(event_bus))
container.register("perception_result", PerceptionResult())
container.register("adaptive_scheduler", AdaptiveScheduler())
```

---

## Plugin System

Two plugin types:

### PluginBase

For plugins that initialize once and don't need per-tick updates.

```python
class MyPlugin(PluginBase):
    name = "my_plugin"
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.event_bus.subscribe("some.event", self._handler)
    
    def shutdown(self):
        pass
```

### TickablePlugin

For plugins that need per-tick updates (input polling, rendering).

```python
class MyTickable(TickablePlugin):
    name = "my_tickable"
    
    def initialize(self, container):
        ...
    
    def update(self, dt: float):
        # Called every tick (30 Hz)
        ...
    
    def shutdown(self):
        ...
```

---

## Event System

### EventBus (queued)

- Thread-safe publish/subscribe
- Events queued during tick, delivered on `flush()`
- Prevents re-entrant handler issues

### Event Types (70+)

- `vision.hand.detected` — hand landmarks + gesture
- `vision.objects.detected` — YOLO bounding boxes
- `CLI_INPUT_RECEIVED` — user typed a command
- `COMMAND_COMPLETED` — command finished
- `cursor.move` — cursor position update

---

## Command System

### CommandBus

```python
command_bus.register_handler("my.command", handler_fn)
command_bus.dispatch(Command(name="my.command", params={}))
```

### Command Lifecycle

1. `command.issued` — queued
2. `command.started` — handler executing
3. `command.completed` / `command.failed` — finished
4. `ResultPipeline.publish(result)` — route to formatters

---

## Vision Pipeline

### FrameBroker

- Camera writes frames at 30fps
- Consumers register via `register_consumer()`
- Each consumer gets frame via `get_frame()`
- Tracks `capture_ts` for frame age calculation

### Perception Threads

- **HandPerceptionPlugin**: MediaPipe GestureRecognizer (VIDEO mode)
- **ObjectSpatialPlugin**: YOLOv8 + solvePnP distance estimation
- Both run in daemon threads, write to PerceptionResult

### AdaptiveScheduler

- Reads profiler metrics every 500ms
- Computes pressure from frame_age + tick_overrun + e2e_latency
- Adjusts YOLO/MediaPipe intervals dynamically
- Skip decisions prevent processing stale frames

---

## GUI Architecture

### UIShell (UI Lifecycle Owner)

UIShell owns the window and all widgets. GUIPlugin is the lifecycle integration layer.

```text
GUIPlugin ──builds──> UIContext ──> UIShell ──owns──> widgets
```

**UIShell responsibilities:**
- Window creation, show/hide/toggle
- Camera panel management
- Panel registration and layout
- Workspace save/restore
- HUD render pipeline (via HUDManager)

**GUIPlugin responsibilities:**
- DI composition (builds UIContext + UIShell)
- Lifecycle integration (start/update/stop)
- Global hotkey registration (Ctrl+Alt+Space)
- Command routing (ui.shell.*, ui.camera.*, ui.panel.*)

### UIShell API

```python
class UIShell:
    def show(self) -> None:      # Show window
    def hide(self) -> None:      # Hide window (no shutdown)
    def toggle(self) -> None:    # Toggle visibility
    @property
    def is_visible(self) -> bool: # Query visibility
```

### GUIPlugin API

```python
class GUIPlugin(TickablePlugin):
    def show_ui(self) -> dict:      # → UIShell.show()
    def hide_ui(self) -> dict:      # → UIShell.hide()
    def toggle_ui(self) -> dict:    # → UIShell.toggle()
    def is_ui_visible(self) -> dict: # → UIShell.is_visible
```

### PySide6 Overlay

- `OverlayWidget` — main transparent window
- `HUDManager` — manages 4 render layers with throttle
- Widgets read from `OverlayModel` only — stateless renderers
- Per-object QPainterPath caching with hash invalidation

### Keyboard Shortcuts (in-window)

- Ctrl+Space / Ctrl+K: Toggle command palette
- F3: Toggle camera
- Ctrl+Shift+1-4: Camera mode switching
- F1: Toggle timeline
- F2: Toggle performance HUD

### Global Hotkey (system-wide, UI-2)

- Ctrl+Alt+Space: Toggle UI visibility (works even when UI is hidden)
- Registered via Win32 `RegisterHotKey` (ctypes)
- Polled in `GUIPlugin.update()` via `PeekMessage`

---

## Profiler

Tracks per-stage timing:
- Camera, YOLO, MediaPipe, VisionAdapter, Render, EventBus flush
- Frame Age (capture → now)
- E2E Latency (capture → perception result → event → render)
- Tick budget usage and overrun count

Hardware budgets (adjusted for USB webcam reality):
- Camera ≤40ms, YOLO ≤70ms, MediaPipe ≤50ms, E2E ≤120ms, Frame Age ≤100ms

---

## Thread Model

| Thread | Purpose |
|--------|---------|
| Main | Tick loop, GUI, EventBus flush, hotkey polling |
| Camera | Frame capture at 30fps |
| HandPerception | MediaPipe gesture recognition |
| ObjectSpatial | YOLO object detection |
| VisionAdapter | PerceptionResult → EventBus events |
| CLI Reader | stdin readline (non-blocking) |

All threads communicate via EventBus/FrameBroker — no direct cross-thread calls.

---

## Schedule Engine (Track A — Implemented)

The Schedule Engine provides deterministic Task & Calendar management with full validation,
audit history, import/export, and a review queue for uncertain items. It is the core of
Mark-1 Track A and is consumed by both the desktop CLI and the planned Web Track B.

### Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **Models** | `aether/task/models.py` | `TaskItem`, `Evidence`, `HistoryEntry`, `ReviewEntry`, `ImportBatch`, enums (`ItemKind`, `ItemStatus`, `InternalStatus`, `ReviewState`), datetime normalization (`normalize_datetime`, `is_date_only`), timezone registry (`TZ_OFFSETS`) |
| **Schema** | `aether/task/schema.py` | SQLite DDL: `items`, `evidence`, `item_history`, `review_queue`, `import_batches`; WAL + FK; CHECK constraints |
| **Migrations** | `aether/task/migrations.py` | Append-only `user_version` migrations (no downgrade) |
| **Repository** | `aether/task/repository.py` | `SqliteScheduleRepository` implementing `IScheduleRepository`; CRUD + evidence + history + review + batches; re-entrant transactions |
| **Service** | `aether/task/service.py` | `ScheduleService` — validated CRUD, optimistic concurrency (`expected_updated_at`), audit history per mutation, import path, evidence attachment |
| **Calendar Queries** | `aether/task/calendar_query.py` | Pure functions: day/week/month views, event date-range coverage, overlap detection (date granularity) |
| **JSON Adapter** | `aether/task/json_adapter.py` | Canonical import/export (format_version "1"), content-hash dedupe, conflict policies (review/update/skip), atomic batch transaction |
| **Plugin** | `aether/plugins/task_plugin.py` | `TaskPlugin` — CLI commands (create, list, complete, cancel, update, calendar, export, import), post-commit `TASK_*` events, config via `task.yaml` |

### Data Model Invariants (Locked)

- **Single table** `items` with `kind` column (`task` | `event`)
- **Task:** `due_date` optional date-only; `all_day` forbidden; timed `start_at`/`end_at` optional
- **Event:** `start_at` required; `all_day=True` keeps date-only strings (no midnight invented); `due_date` forbidden
- **Date-only** (`YYYY-MM-DD`) never becomes midnight; only allowed when `all_day=True`
- **Offset-aware datetimes** preserved as-is; naive datetimes gain item timezone at single write boundary (`ScheduleService._validate`)
- **Review queue** — `review_queue` table with unique pending row per item (`idx_review_one_pending`); `InternalStatus.NEEDS_CONFIRMATION` on item + `ReviewState.PENDING` row = extraction uncertainty
- **Import batches** — `import_batches` table with `content_hash` (canonical JSON SHA-256) for file-level dedupe
- **History** — append-only `item_history` (no FK), survives item deletion; actions: CREATED, UPDATED, COMPLETED, CANCELLED, DELETED, IMPORTED, REVIEWED

### Validation Rules (R1 + R6)

- **R1 (Chronology):** Compare instants, not raw strings. Naive datetimes → item tz; aware preserved. Fixes false-reject/accept with mixed offsets (e.g., `14:00+09:00` vs `12:00+07:00` equal).
- **R6 (Date-only):** Bare `YYYY-MM-DD` in `start_at`/`end_at` rejected when `all_day=False`. `all_day=True` keeps date-only.

### Commands (via `task_plugin`)

| Command | Description |
|---------|-------------|
| `task.create` | Create task or event (kind, title, due_date/start_at/end_at, all_day, tz) |
| `task.list` | List items (filter by kind, status) |
| `task.complete` | Complete a pending task |
| `task.cancel` | Cancel a pending task or event |
| `task.update` | Update allowed fields (optimistic concurrency via `expected_updated_at`) |
| `task.calendar` | Day/week/month calendar views |
| `task.export` | Export items to canonical JSON |
| `task.import` | Import JSON (conflict policy: review/update/skip) |

### Configuration

```yaml
# config/task.yaml
task:
  db_path: "data/tasks.db"
```

---

## Web Integration (Track B — Planned)

**Status:** Architecture direction only. Not implemented. API contract not yet designed.

### High-Level Architecture

```
Browser (HTML/CSS/JS)
       │
       ▼
PHP Web Backend (stateless request handlers)
       │
       ▼ HTTP API (contract TBD)
Python FastAPI Service (wraps Track A ScheduleService)
       │
       ▼ In-process
ScheduleService → SqliteScheduleRepository → data/tasks.db
```

### Design Constraints

- **Single writer:** `ScheduleService` (Python) remains the sole writer to `data/tasks.db`. PHP never writes SQLite directly.
- **Validation authority:** All business rules (R1, R6, kind invariants, review lifecycle) enforced in `ScheduleService`. PHP validates only transport/format.
- **Shared database:** `data/tasks.db` (SQLite WAL) read by both; Python service coordinates writes.
- **No schema migration** in Track B — Track A owns schema via `user_version` migrations.
- **Review queue exposure:** Web UI must surface `review_queue` items (extraction uncertainty + import conflicts) for human resolution.
- **Auth:** Local-only for MVP (no multi-user). Session/token design TBD.
- **No external AI:** Extraction (Phase 4) stays deterministic; no LLM calls from PHP or Python.

### Open Questions (to resolve before API design)

1. **Transport:** REST (FastAPI) vs gRPC vs JSON-RPC over HTTP?
2. **Error model:** How to surface `ScheduleValidationError`, `ScheduleConflictError`, `ScheduleNotFoundError` to PHP?
3. **Review resolution:** Single endpoint `POST /reviews/{id}/resolve` with `{decision: confirm|edit|reject, fields?}`?
4. **Batch import:** Reuse `task.import` contract or dedicated web endpoint?
5. **Real-time updates:** WebSocket / SSE for live calendar/task changes?
6. **File upload:** Evidence attachment via multipart or base64 JSON?

*These questions are tracked for the API design phase. No answers are recorded here.*

---

## Design Principles (Post-v1)

1. **Every commit adds user-facing capability** — no more infrastructure-only changes
2. **Backend v1 is frozen** — fix only bugs or security issues
3. **Two-track delivery** — Track A (Schedule Engine) stabilizes first; Track B (Web) consumes it
4. **Test everything** — 1,349+ tests, run before every commit
5. **No external AI egress** — provider stays `echo`; deterministic rules only