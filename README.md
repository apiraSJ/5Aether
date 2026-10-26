```
    _    ____   ____ _   _ _____ _   _ ______  __
   / \  |  _ \ / ___| | | | ____| \ | | __ \ \ / /
  / _ \ | |_) | |   | |_| |  _| |  \| |  _ \\ V /
 / ___ \|  _ <| |___|  _  | |___| |\  | |_) || |
/_/   \_\_| \_\\____|_| |_|_____|_| \_|____/ |_|
```

> Spatial Intelligence AI — Built for desktop today, architected for XR tomorrow.
> **Mark-1: Web Task & Calendar Assistant** — Track A (Python Schedule Engine) + Track B (Web UI)

Aether is a command-driven AI Spatial Assistant with a plugin-based runtime, event-driven architecture, and vision pipeline. Boot → Tick → Shutdown lifecycle, 70+ event types, config-driven plugins, and a vision pipeline targeting ≤120ms E2E latency.

**Backend v1.0.0** — Architecture Stable (tagged `backend-v1.0.0`)
**UI Lifecycle** — UI-0 through UI-1 complete, UI-2 in progress
**Mark-1 Track A (Schedule Engine)** — Core schedule engine implemented; R1/R6 chronology and date-only validation rules are documented below. Phase 4 temporal extraction is in progress.
**Mark-1 Track B (Web Application)** — In progress / partially implemented: FastAPI task/calendar API and HTML/CSS/JS frontend are present. Verify the current test count and commit before publishing release claims.

---

## Quick Start

### Windows (one-click) — Desktop Vision Mode

```bat
git clone <repo-url> Aether
cd Aether
scripts\setup.bat       # creates venv + installs everything
scripts\start.bat       # launches Aether in vision mode
```

### Any Platform — Desktop

```bash
git clone <repo-url> Aether
cd Aether
python -m venv .venv
.venv\Scripts\activate              # Windows
pip install -e ".[full]"            # install with all extras
python -m aether --mode vision      # launch with camera + GUI
```

### Run Modes (Desktop)

```bash
python -m aether --mode vision       # Full vision pipeline + GUI overlay
python -m aether --background        # Start with UI hidden (background mode)
python -m aether --profile           # Performance profiling (30s default)
python -m aether --profile --duration 60  # Custom duration
```

### Profiling

```bat
scripts\profile.bat 30       # 30-second hardware validation
```

### Tests

```bash
python -m pytest tests/ -v           # Run the full test suite
```

---

## Mark-1 Track B — Web (In Progress / Partial)

Track B has a Python FastAPI backend and an HTML/CSS/JavaScript frontend. The browser UI calls the API; PHP is not part of the documented implementation.

### Web Components

- `aether/api/` — FastAPI application, server setup, schemas, dependencies, middleware, and error handling.
- `aether/api/routes/tasks.py` — task CRUD and task actions.
- `aether/api/routes/calendar.py` — calendar day/week/month queries.
- `web/` — frontend entry point (`index.html`), application logic (`app.js`), and styles (`styles.css`).
- `web/frontend/` — packaged frontend copy.
- `config/web.yaml` — web-mode configuration.
- `data/tasks.db` — SQLite schedule data shared with the Python schedule engine.

The API is mounted under `/api/v1`; `/health` provides a health endpoint, and the root route serves the web UI. The Python schedule engine remains responsible for schedule data access and writes.

### Quick Start (Web)

From the repository root, create and activate a virtual environment, then install the server extra:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e ".[server]"
```

Start the application in web mode using the repository entry point:

```bash
python -m aether --mode web
```

Then open the local address and port reported by the server in your browser. Check `config/web.yaml` for the configured web/server settings. If your checkout exposes a different web-mode command, use `python -m aether --help` to inspect the available modes.

### Current Scope

- Task list, creation, editing, completion, and cancellation.
- Calendar day/month views and backend day/week/month query support.
- API concurrency handling for edits using `If-Match` / `updated_at`.
- Shared `data/tasks.db` storage through the Python schedule engine.

The review-queue UI and broader extraction workflow should be treated as roadmap work unless confirmed in the current implementation and tests.

---

## UI Lifecycle (Desktop)

### Boot Modes

| Mode | Command | Behavior |
|------|---------|----------|
| Normal | `python -m aether` | UI visible, runtime active |
| Background | `python -m aether --background` | UI hidden, runtime active |

### Runtime Commands

| Command | Description |
|---------|-------------|
| `ui.shell.show` | Show the Aether UI window |
| `ui.shell.hide` | Hide the Aether UI window |
| `ui.shell.toggle` | Toggle Aether UI window visibility |
| `ui.shell.is_visible` | Check if Aether UI window is visible |

### Global Hotkey (UI-2, planned)

- **Ctrl+Alt+Space**: Toggle UI visibility (system-wide, works even when UI is hidden)

### Lifecycle Semantics

```
Background ≠ Shutdown
Hide ≠ Shutdown
Quit = real graceful shutdown
```

---

## Architecture

### One-Way Data Flow

```text
Camera ──▶ FrameBroker ──▶ YOLO / MediaPipe ──▶ PerceptionResult
                                                        │
                                                        ▼
                                                VisionEventAdapter
                                                        │
                                                        ▼
                                                   EventBus (queued)
                                                        │
                                                        ▼
                                               OverlayController ──▶ OverlayModel ──▶ Widgets
```

### Core Systems

| System | Purpose |
|--------|---------|
| **EventBus** | Thread-safe pub/sub, queued delivery, 70+ event types |
| **CommandBus** | Command dispatch with handlers, lifecycle events |
| **ResultPipeline** | CommandResult → notification, history, layout |
| **FrameBroker** | Central frame distribution, overwrite tracking |
| **AdaptiveScheduler** | Dynamic rate control based on profiler metrics |
| **DI Container** | Service registration and resolution |
| **Plugin System** | `PluginBase` / `TickablePlugin` with config from YAML |

### Data Flow: Input → Command → Result

```text
[CLI]  [Camera]  [Gesture]  [Keyboard]  [Voice]
  │       │         │           │          │
  └───────┴─────────┴───────────┴──────────┘
                    │
                    ▼
         EventBus: CLI_INPUT_RECEIVED / vision.*
                    │
                    ▼
         IntentResolver → resolve text → Command
                    │
                    ▼
         CommandBus.dispatch(Command)
                    │
                    ▼
         handler(command) → returns result
                    │
                    ▼
         ResultPipeline.publish(CommandResult)
```

---

## System Adapter Layer

`systems/` contains the host/platform adapter layer and discovers system modules through `manifest.yaml`. The current `systems/mark1/` adapter wraps the existing Mark-1 services; it is an integration layer, not a relocation of the schedule engine or API code. See the architecture and capability documents for the intended boundaries and current audit findings.

---

## Mark-1 Track A — Schedule Engine (Implemented)

### Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **Models** | `aether/task/models.py` | `TaskItem`, `Evidence`, `HistoryEntry`, `ReviewEntry`, `ImportBatch`, enums, datetime normalization, timezone registry |
| **Schema** | `aether/task/schema.py` | SQLite DDL: `items`, `evidence`, `item_history`, `review_queue`, `import_batches` |
| **Migrations** | `aether/task/migrations.py` | Append-only `user_version` migrations |
| **Repository** | `aether/task/repository.py` | `SqliteScheduleRepository` implementing `IScheduleRepository` |
| **Service** | `aether/task/service.py` | `ScheduleService` — validated CRUD, optimistic concurrency, audit history |
| **Calendar Queries** | `aether/task/calendar_query.py` | Day/week/month views, overlap detection |
| **JSON Adapter** | `aether/task/json_adapter.py` | Canonical import/export, dedupe, conflict policies |
| **Temporal Extraction** | `aether/task/extraction.py` | Phase 4 extraction helper; consult `docs/PHASE4_SPEC.md` for intended behavior and status |
| **Plugin** | `aether/plugins/task_plugin.py` | CLI commands + `TASK_*` events |
| **HTTP API** | `aether/api/` | FastAPI task/calendar endpoints for Track B |

### Data Model Invariants (Locked)

- **Single table** `items` with `kind` (`task` | `event`)
- **Task:** `due_date` optional date-only; `all_day` forbidden
- **Event:** `start_at` required; `all_day=True` keeps date-only (no midnight); `due_date` forbidden
- **Date-only** never becomes midnight; only allowed with `all_day=True`
- **Offset-aware datetimes** preserved; naive gain item tz at write boundary
- **Review queue** — unique pending row per item; `NEEDS_CONFIRMATION` + `PENDING` = uncertainty
- **Import batches** — canonical SHA-256 content hash for file-level dedupe
- **History** — append-only, survives deletion

### Validation Rules (Locked)

- **R1 (Chronology):** Compare instants, not raw strings. Naive → item tz; aware preserved.
- **R6 (Date-only):** Bare `YYYY-MM-DD` in `start_at`/`end_at` rejected when `all_day=False`.

### Commands

| Command | Description |
|---------|-------------|
| `task.create` | Create task or event |
| `task.list` | List items (filter by kind, status) |
| `task.complete` | Complete a pending task |
| `task.cancel` | Cancel a pending task or event |
| `task.update` | Update fields (optimistic concurrency) |
| `task.calendar` | Day/week/month views |
| `task.export` | Export items to canonical JSON |
| `task.import` | Import JSON (review/update/skip) |

### Configuration

```yaml
# config/task.yaml
task:
  db_path: "data/tasks.db"
```

---

## Project Structure

```text
Aether/
├── aether/                        # Main Python package
│   ├── api/                       # FastAPI app, server, schemas, middleware, routes
│   │   └── routes/                # Task and calendar API endpoints
│   ├── ai/                        # AI context, intent/provider, memory and tools
│   ├── services/                  # Runtime-facing service adapters
│   ├── domain/                    # Shared domain models
│   ├── core/                      # Runtime foundation
│   │   ├── application.py         # Boot → Tick → Shutdown lifecycle
│   │   ├── command.py             # Command dataclass
│   │   ├── command_bus.py         # Command dispatch + handler registry
│   │   ├── command_registry.py    # Autocomplete, help, categories
│   │   ├── command_result.py      # CommandResult dataclass
│   │   ├── event_bus_v2.py        # Queued EventBus with flush
│   │   ├── event_type.py          # 70+ event type constants
│   │   ├── frame_broker.py        # Frame distribution + consumer registry
│   │   ├── intent_resolver.py     # IIntentResolver protocol
│   │   ├── profiler.py            # Pipeline timing + hardware budgets
│   │   ├── adaptive_scheduler.py  # Dynamic rate control
│   │   ├── plugin.py              # PluginBase, TickablePlugin, PluginMetadata
│   │   ├── service_container.py   # DI container
│   │   ├── result_pipeline.py     # CommandResult routing
│   │   └── virtual_cursor.py      # Cursor position tracking
│   ├── plugins/                   # Feature plugins
│   │   ├── cli_plugin.py          # Interactive CLI (readline)
│   │   ├── system_plugin.py       # System commands (ping, info, shutdown)
│   │   ├── system_commands_plugin.py  # CommandRegistry + handlers
│   │   ├── rule_intent_plugin.py  # NL → Command (14 regex patterns)
│   │   ├── intent_resolver_plugin.py  # Event-driven intent resolution
│   │   ├── result_formatter_plugin.py # Colored CLI output
│   │   ├── gui_plugin.py          # GUIPlugin — UIShell lifecycle, hotkey
│   │   ├── memory_plugin.py       # Memory CRUD commands
│   │   └── task_plugin.py         # Task/Calendar CLI + events
│   ├── vision/                    # Vision pipeline
│   │   └── plugins.py             # VisionAdapterPlugin (state → events)
│   ├── phase_b/                   # Legacy bridge (CommandExecutor)
│   ├── phase_c/                   # Input adapters
│   │   ├── gesture_input_plugin.py    # Gesture → command mapping
│   │   └── voice_input_plugin.py      # Voice → command mapping
│   ├── phase_d/                   # Perception + cursor
│   │   ├── camera_plugin.py       # CameraThread + FrameBroker
│   │   ├── hand_plugin.py         # MediaPipe GestureRecognizer
│   │   ├── object_plugin.py       # YOLOv8 + solvePnP
│   │   └── cursor_plugin.py       # Cursor + PinchClick
│   ├── ui/                        # GUI widgets + lifecycle (tree below is not exhaustive)
│   │   ├── ui_shell.py            # UIShell — owns window, camera, panels
│   │   ├── ui_context.py          # UIContext — DI bundle for widgets
│   │   ├── camera_widget.py       # Camera feed widget
│   │   ├── overlay_widget.py      # QPainterPath cache, QStaticText
│   │   ├── object_list_widget.py  # Object list panel
│   │   ├── gesture_widget.py      # Gesture status display
│   │   ├── status_widget.py       # System status display
│   │   ├── timeline_widget.py     # Event timeline
│   │   └── hud_manager.py         # Multi-layer throttle scheduler
│   ├── task/                      # Mark-1 Schedule Engine (Track A)
│   │   ├── extraction.py           # Phase 4 temporal extraction helper
│   │   ├── models.py              # TaskItem, Evidence, HistoryEntry, ReviewEntry, ImportBatch
│   │   ├── schema.py              # SQLite DDL
│   │   ├── migrations.py          # user_version migrations
│   │   ├── repository.py          # SqliteScheduleRepository
│   │   ├── service.py             # ScheduleService
│   │   ├── calendar_query.py      # Calendar views (pure functions)
│   │   ├── json_adapter.py        # Canonical JSON import/export
│   │   └── __init__.py            # Exports
│   ├── memory/                    # Memory persistence and models
│   └── config/                    # Config loader
├── systems/                       # Manifest-discovered system adapters
│   └── mark1/                     # Mark-1 adapter over existing services
├── web/                           # Mark-1 browser frontend
│   ├── index.html                 # Main page
│   ├── app.js                     # API client and UI behavior
│   ├── styles.css                 # Frontend styles
│   └── frontend/                  # Packaged frontend copy
├── config/
│   ├── default.yaml               # Base config
│   ├── vision.yaml                # Vision plugin load order + settings
│   ├── task.yaml                  # Task/Calendar config
│   ├── web.yaml                   # Web/API mode settings
│   ├── ai.yaml                    # AI provider/settings
│   ├── memory.yaml                # Memory settings
│   └── gesture.yaml               # Gesture settings
├── scripts/
│   ├── setup.bat                  # One-click setup
│   ├── start.bat                  # Launch Aether
│   ├── tick.bat                   # Tick mode launcher
│   └── profile.bat                # Performance profiler
├── models/                        # ML weights (gitignored)
├── data/                          # Runtime data (gitignored)
│   ├── memory.db                  # Memory Core SQLite
│   └── tasks.db                   # Mark-1 Schedule SQLite (gitignored)
├── docs/                          # Architecture, roadmap, audits and phase specs
├── tests/                         # Test suite (run locally for current count)
├── pyproject.toml
├── start.py                        # Environment-aware launcher (if present in checkout)
└── main.py                         # Legacy entry point
```

---

## Hardware Requirements

| Component | Budget | Typical |
|-----------|--------|---------|
| Camera | ≤40ms P95 | 33ms (30fps USB) |
| YOLO | ≤70ms P95 | 35-45ms |
| MediaPipe | ≤50ms P95 | 20-38ms |
| E2E Latency | ≤120ms P95 | 65-105ms |
| Frame Age | ≤100ms P95 | 63-98ms |
| Tick | ≤33ms budget | 20ms avg |

---

## Configuration

Settings are split across the configuration files under `config/`, including `config/vision.yaml`, `config/task.yaml`, and `config/web.yaml`:

```yaml
# config/task.yaml
task:
  db_path: "data/tasks.db"
```

```yaml
# config/vision.yaml (excerpt)
app:
  name: "Aether"
  version: "1.0.0"
  tick_rate: 30
  mode: "vision"

event_bus:
  queued: true

adaptive_scheduler:
  debug: false

plugins:
  - module: "aether.plugins.system_plugin"
    class: "SystemPlugin"
  - module: "aether.plugins.gui_plugin"
    class: "GUIPlugin"
  - module: "aether.plugins.task_plugin"
    class: "TaskPlugin"
  # ... (see full config for all plugins)
```

---

## Gesture Reference (Desktop)

| Gesture | Command | Description |
|---------|---------|-------------|
| `Open_Palm` | `gesture_open_palm` | Toggle UI |
| `Closed_Fist` | `gesture_closed_fist` | Cancel/Close |
| `Pointing_Up` | `gesture_pointing_up` | Move cursor |
| `Thumb_Up` | `gesture_thumb_up` | Confirm |
| `Thumb_Down` | `gesture_thumb_down` | Reject |
| `Victory` | `gesture_victory` | Developer tools |
| `ILoveYou` | `gesture_iloveyou` | Settings |
| Pinch | `cursor_click` | Click at cursor |

---

## Testing

Run the suite in the active environment and use the resulting summary as the source of truth for the test count.

```bash
python -m pytest tests/ -v
python -m pytest tests/test_ui_lifecycle.py -v  # UI lifecycle tests
python -m pytest tests/test_cli_system.py -v    # CLI + intent tests
python -m pytest tests/test_task_*.py -v        # Mark-1 Track A tests
python -m pytest tests/test_api_*.py -v          # Mark-1 API tests
```

---

## Documentation

| File | Contents |
|------|----------|
| `docs/ARCHITECTURE.md` | System architecture reference (incl. Schedule Engine + Web Integration) |
| `docs/ROADMAP.md` | Development roadmap (Track A + Track B) |
| `docs/UI-2-plan.md` | UI-2 Global Hotkey implementation plan |
| `docs/workspace.md` | Workspace + Layout system |
| `docs/REVIEW_AUDIT.md` | Mark-1 Phase 0 review audit |
| `docs/ARCHITECTURE_AUDIT.md` | Architecture audit and known design gaps |
| `docs/CAPABILITY_INVENTORY.md` | Inventory of implemented capabilities |
| `docs/PHASE4_SPEC.md` | Phase 4 Temporal Extraction specification (check document status before treating it as final) |
| `docs/AI_ASSISTANT_BASELINE.md` | Historical baseline (Sep 2026) |

---

## Known Issues and Roadmap

Use `docs/ROADMAP.md` for planned work and `docs/ARCHITECTURE_AUDIT.md` for the latest recorded architecture findings. The performance observations below are historical baseline notes, not a guarantee that they describe the current machine or checkout.

| Historical observation | Potential impact | Follow-up |
|-------------------------|------------------|-----------|
| Camera P95 around 48ms | Occasional frame drops | Re-measure on target hardware |
| Tick overrun around 30% | GUI jank under load | Re-profile and optimize budgets |
| YOLO around 5–8 Hz | Object detection delay | Re-profile scheduler and model settings |
| CLI degraded mode on Windows | No tab-completion | Check optional readline support |

Before publishing a release, re-run the test suite and update test counts, commit IDs, and performance figures from current results. Track B is partially implemented; do not describe planned review-queue or extraction UI as complete unless verified.


---

## Design Principles

1. **Event-Driven** — No module calls another directly. All communication through EventBus.
2. **One-Way Data Flow** — Camera → FrameBroker → Perception → Events → UI. No cycles.
3. **Widgets are Stateless** — Paint from OverlayModel only. No widget modifies state.
4. **Plugins Never Communicate** — EventBus only. No direct plugin-to-plugin calls.
5. **Thread-Safe** — FrameBroker, EventBus, CommandBus all use locks/queues.
6. **Config-Driven** — Scheduler debug, plugin load order, hardware budgets all in YAML.
7. **Two-Track Delivery** — Track A (Schedule Engine) stabilizes first; Track B (Web) consumes it.
8. **No External AI Egress** — Provider stays `echo`; deterministic rules only.

---

## License

MIT