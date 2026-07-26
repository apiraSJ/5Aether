# Aether — AI Spatial Assistant

> Make the brain useful to people.

Aether is a command-driven AI Spatial Assistant with a plugin-based runtime, event-driven architecture, and vision pipeline. Built for desktop today, architected for XR Smart Glasses tomorrow.

**Backend v1.0.0** — Architecture Stable (tagged `backend-v1.0.0`)

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
python -m aether --profile           # Performance profiling (30s default)
python -m aether --profile --duration 60  # Custom duration
```

### Profiling

```bat
scripts\profile.bat 30       # 30-second hardware validation
```

### Tests

```bash
python -m pytest tests/ -v
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
│   │   ├── gui_plugin.py          # PySide6 Vision HUD
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
│   ├── ui/                        # GUI widgets
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
├── tests/                         # 128 tests
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
  version: "0.3.0"
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
python -m pytest tests/ -v           # All 128 tests
python -m pytest tests/test_cli_system.py -v  # CLI + intent tests
```

---

## Documentation

| File | Contents |
|------|----------|
| `docs/ARCHITECTURE.md` | System architecture reference |
| `docs/ROADMAP.md` | Development roadmap |

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
