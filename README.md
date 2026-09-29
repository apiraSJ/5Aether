```
     _    ____   ____ _   _ _____ _   _ ______  __
    / \  |  _ \ / ___| | | | ____| \ | | __ \ \ / /
   / _ \ | |_) | |   | |_| |  _| |  \| |  _ \\ V /
  / ___ \|  _ <| |___|  _  | |___| |\  | |_) || |
 /_/   \_\_| \_\\____|_| |_|_____|_| \_|____/ |_|
```

> Spatial Intelligence AI — Built for desktop today, architected for XR tomorrow.

Aether is a command-driven AI Spatial Assistant with a plugin-based runtime, event-driven architecture, and vision pipeline. Boot → Tick → Shutdown lifecycle, 70+ event types, config-driven plugins, and a vision pipeline targeting ≤120ms E2E latency.

**Backend v1.0.0** — Architecture Stable (tagged `backend-v1.0.0`)
**UI Lifecycle** — UI-0 through UI-1 complete, UI-2 in progress

---

## Quick Start

### Windows (one-click)

```bat
git clone <repo-url> Aether
cd Aether
scripts\setup.bat       # creates venv + installs everything
scripts\start.bat       # launches Aether in vision mode
```

### Any platform

```bash
git clone <repo-url> Aether
cd Aether
python -m venv .venv
.venv\Scripts\activate              # Windows
pip install -e ".[full]"            # install with all extras
python -m aether --mode vision      # launch with camera + GUI
```

### Run modes

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
python -m pytest tests/ -v           # All 921 tests
```

---

## UI Lifecycle

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

## Project Structure

```text
Aether/
├── aether/                        # Source code
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
│   │   └── memory_plugin.py       # Memory CRUD commands
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
│   ├── ui/                        # GUI widgets + lifecycle
│   │   ├── ui_shell.py            # UIShell — owns window, camera, panels
│   │   ├── ui_context.py          # UIContext — DI bundle for widgets
│   │   ├── camera_widget.py       # Camera feed widget
│   │   ├── overlay_widget.py      # QPainterPath cache, QStaticText
│   │   ├── object_list_widget.py  # Object list panel
│   │   ├── gesture_widget.py      # Gesture status display
│   │   ├── status_widget.py       # System status display
│   │   ├── timeline_widget.py     # Event timeline
│   │   └── hud_manager.py         # Multi-layer throttle scheduler
│   ├── memory/                    # Memory service
│   │   └── memory_service.py      # SQLite (WAL) persistence
│   └── config/                    # Config loader
├── config/
│   └── vision.yaml                # Plugin load order + settings
├── scripts/
│   ├── setup.bat                  # One-click setup
│   ├── start.bat                  # Launch Aether
│   ├── tick.bat                   # Tick mode launcher
│   └── profile.bat                # Performance profiler
├── models/                        # ML weights (gitignored)
├── tests/                         # 921 tests
├── pyproject.toml
└── main.py                        # Legacy entry point
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

All settings in `config/vision.yaml`:

```yaml
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
  # ... (see full config for all plugins)
```

---

## Gesture Reference

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

```bash
python -m pytest tests/ -v           # All 921 tests
python -m pytest tests/test_ui_lifecycle.py -v  # UI lifecycle tests (30)
python -m pytest tests/test_cli_system.py -v    # CLI + intent tests
```

---

## Documentation

| File | Contents |
|------|----------|
| `docs/ARCHITECTURE.md` | System architecture reference |
| `docs/ROADMAP.md` | Development roadmap |
| `docs/UI-2-plan.md` | UI-2 Global Hotkey implementation plan |
| `docs/workspace.md` | Workspace + Layout system |
| `docs/AI_ASSISTANT_BASELINE.md` | Baseline state before AI integration |

---

## Backend v1.0.0 — Known Issues

| Issue | Impact | Fix planned |
|-------|--------|-------------|
| Camera P95=48ms | Occasional frame drop | Hardware upgrade |
| Tick overrun ~30% | GUI jank under load | Budget optimization |
| YOLO ~5-8 Hz | Object detection delay | Scheduler tuning v1.0.1 |
| CLI degraded mode | No tab-completion on Windows | `pip install pyreadline3` |

---

## Design Principles

1. **Event-Driven** — No module calls another directly. All communication through EventBus.
2. **One-Way Data Flow** — Camera → FrameBroker → Perception → Events → UI. No cycles.
3. **Widgets are Stateless** — Paint from OverlayModel only. No widget modifies state.
4. **Plugins Never Communicate** — EventBus only. No direct plugin-to-plugin calls.
5. **Thread-Safe** — FrameBroker, EventBus, CommandBus all use locks/queues.
6. **Config-Driven** — Scheduler debug, plugin load order, hardware budgets all in YAML.

---

## License

MIT
