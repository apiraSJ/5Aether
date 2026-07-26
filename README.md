# Aether — AI Spatial Assistant

> Build the brain before giving it better eyes.

Aether is a modular, event-driven AI Spatial Assistant for desktop today, architected for XR Smart Glasses tomorrow. It combines computer vision (MediaPipe GestureRecognizer + YOLOv8), spatial awareness (solvePnP), memory, task management, and a command system into a single extensible platform.

---

## Quick Start

### Windows (one-click)

```
git clone <repo-url> Aether
cd Aether
setup.bat       # creates venv + installs everything
start.bat       # launches Aether
```

### Any platform

```bash
git clone <repo-url> Aether
cd Aether
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[full]"        # install with all extras
python -m aether                # headless boot
```

### Run modes

```bash
python -m aether                        # headless — boot proof + idle
python -m aether --mode tick            # 30Hz tick loop with plugins
python -m aether --mode headless        # same as default
python -m aether --strict-plugins       # fail-fast on plugin errors
python start.py --tick                  # cross-platform launcher
```

### Tests

```bash
python -m pytest tests/phase_a/ -v
```

---

## Architecture Overview

```text
                          ┌──────────────────────────┐
                          │         AETHER            │
                          │                           │
                          │   ┌───────────────────┐   │
                          │   │     EventBus       │   │
                          │   │  (69 event types)  │   │
                          │   └──────┬────┬────┬──┘   │
                          │          │    │    │       │
                          │     ┌────┘ ┌──┘ ┌──┘      │
                          │     ▼      ▼    ▼          │
                          │  Memory  Tasks  Commands   │
                          │     ▲      ▲    ▲          │
                          │  JSON    JSON  Handler     │
                          │                           │
                          │   ┌───────────────────┐   │
                          │   │ Perception Pipeline │   │
                          │   │  ┌─────┐ ┌─────┐  │   │
                          │   │  │Hand │ │YOLO │  │   │
                          │   │  │Plug.│ │Plug.│  │   │
                          │   │  └──┬──┘ └──┬──┘  │   │
                          │   │     └───┬────┘     │   │
                          │   │   ┌─────▼──────┐  │   │
                          │   │   │ FrameBroker │  │   │
                          │   │   └─────┬──────┘  │   │
                          │   └─────────┼─────────┘   │
                          │        ┌────▼────┐        │
                          │        │ Camera   │        │
                          │        └─────────┘        │
                          └──────────────────────────┘
```

### Two Entry Points

| Entry Point | UI Framework | Purpose | Command |
|-------------|-------------|---------|---------|
| `main.py` | DearPyGui + OpenCV | Camera pipeline — gesture recognition, YOLO detection, HUD overlay | `python main.py` |
| `brain_main.py` | PySide6 overlay | Brain-only — hotkeys, commands, memory, context (no camera) | `python brain_main.py` |

Both share the same EventBus, memory, command, and context systems.

---

## Project Structure

```text
Aether/
├── main.py                     # Vision pipeline entry point
├── brain_main.py               # Brain-only entry point (PySide6)
├── requirements.txt            # Python dependencies
├── config/
│   ├── desktop.yaml            # Desktop profile (camera, model, gesture, HUD)
│   └── default.yaml            # Minimal defaults
├── core/                       # Application foundation
│   ├── engine.py               # AetherEngine — lifecycle manager
│   ├── app.py                  # AetherApp — top-level owner (EventBus + Plugins + Settings)
│   ├── event_bus.py            # EventBus — thread-safe pub/sub (69 event types)
│   ├── module.py               # Module ABC + ModuleManager
│   ├── plugin_manager.py       # Plugin ABC + PluginManager
│   ├── settings.py             # YAML config with deep merge
│   ├── frame_broker.py         # Thread-safe frame distribution hub
│   ├── camera.py               # Synchronous camera wrapper
│   ├── camera_thread.py        # Threaded camera capture
│   ├── detector.py             # YOLOv8 inference wrapper
│   ├── perception_pipeline.py  # Plugin orchestrator per frame
│   ├── perception_worker.py    # Background ML pipeline (throttled)
│   ├── cursor_manager.py       # Camera→screen coordinate mapping + smoothing
│   ├── gesture_router.py       # Gesture→action routing with cooldown
│   ├── action_queue.py         # Thread-safe bridge: perception → UI
│   ├── interaction_mode.py     # Mode state machine (PASSIVE→POINTING)
│   ├── renderer.py             # OpenCV HUD drawing
│   ├── telemetry.py            # FPS/latency tracking
│   ├── performance.py          # Block timing + rolling averages
│   └── logger.py               # Logging setup
├── perception/                 # Daemon perception threads
│   ├── hand_plugin.py          # MediaPipe GestureRecognizer thread
│   └── object_plugin.py        # YOLO + solvePnP thread
├── vision/                     # Computer vision algorithms
│   ├── hand_tracker.py         # MediaPipe HandLandmarker wrapper
│   ├── hand_landmarks.py       # 21 landmark constants + connections
│   ├── gesture_engine.py       # Rule-based gesture recognizer (fallback)
│   ├── gesture_actions.py      # Gesture→Action enums + finger utilities
│   ├── gesture_executor.py     # Gesture→EventBus bridge
│   ├── spatial.py              # PnP distance estimator
│   ├── pnp.py                  # Standalone solvePnP utility
│   ├── calibration.py          # Camera intrinsics loader
│   ├── geometry.py             # 3D visualization helpers
│   ├── command_confirmation.py # 2-step confirm/cancel flow
│   └── tracking.py             # Placeholder tracker (sequential IDs)
├── interface/                  # PySide6 UI (brain-only mode)
│   ├── ui.py                   # AetherUI — floating overlay, 3 panels
│   ├── ui_manager.py           # UIManager — coordinates HomeMenu + StatusBar
│   ├── home_menu.py            # HomeMenu — gesture-driven vertical chain menu
│   ├── cursor_overlay.py       # CursorOverlay — holographic cursor widget
│   ├── hud_renderer.py         # OpenCV HUD drawing functions
│   └── status_bar.py           # StatusBar — top-right info overlay
├── command/                    # Event-driven command system
│   ├── command.py              # Command dataclass + BaseCommand ABC + Registry
│   └── handler.py              # CommandHandler — execute + emit events
├── memory/                     # Data models + persistence
│   ├── models.py               # SpatialObject, Task, EventRecord dataclasses
│   ├── storage.py              # MemoryStorage — user preferences JSON
│   └── object_memory.py        # ObjectMemory — in-memory CRUD cache
├── database/                   # JSON file storage layer
│   ├── storage.py              # JsonStorage — atomic write key-value store
│   ├── objects.py              # ObjectStore
│   ├── tasks.py                # TaskStore
│   └── events.py               # EventStore (append-only log)
├── tasks/
│   └── manager.py              # TaskManager — lifecycle CRUD
├── context/
│   └── context_manager.py      # Active window + CPU/RAM monitoring
├── interaction/                # UI interaction system
│   ├── interaction_manager.py  # Central coordinator
│   ├── state_machine.py        # FSM: IDLE→TRACKING→MENU_OPEN/PANEL_OPEN
│   └── focus_manager.py        # Widget hit-testing for cursor hover
├── models/                     # ML model weights
│   ├── gesture_recognizer.task # MediaPipe GestureRecognizer
│   └── hand_landmarker.task    # MediaPipe HandLandmarker (legacy)
├── tests/                      # pytest test suite
│   ├── test_gesture_actions.py
│   ├── test_event_bus.py
│   ├── test_database.py
│   ├── test_spatial.py
│   ├── test_memory.py
│   ├── test_tasks.py
│   ├── test_perception_worker.py
│   └── test_interaction.py
└── docs/                       # Documentation
    ├── ARCHITECTURE.md
    ├── ROADMAP.md
    ├── COMMANDS.md
    ├── EVENTS.md
    ├── MEMORY.md
    ├── PLUGINS.md
    ├── API.md
    └── CONTRIBUTING.md
```

---

## Core Concepts

### EventBus (Central Nervous System)

All modules communicate exclusively through the EventBus — no direct coupling. 69 event types across system, UI, input, command, task, vision, context, memory, and status categories. Thread-safe subscribe/emit.

### Perception Pipeline (Eyes)

Camera frames flow through `FrameBroker` to daemon perception threads. `HandPerceptionPlugin` runs MediaPipe GestureRecognizer for 8 native gestures. `ObjectSpatialPlugin` runs YOLOv8 for 80-class detection + solvePnP for Z-distance estimation. Both emit events on the EventBus.

### Gesture Router (Translation Layer)

Gestures detected by perception threads are routed through `GestureRouter` which maps them to UI actions with cooldown dedup, hold-time gating, and edge-triggered pinch detection. Actions flow through a thread-safe `ActionQueue` to ensure Qt widgets are updated on the main thread.

### Cursor Manager (Spatial Mapping)

Maps normalized camera coordinates to screen pixels using contain-mode aspect-ratio preservation. Applies adaptive smoothing, dead-zone filtering, and velocity prediction for low-latency cursor movement. Freezes during pinch for click accuracy.

### Command System (Intelligence)

Event-driven commands flow through `CommandHandler` which tracks status (PENDING→EXECUTING→COMPLETED/FAILED) and emits lifecycle events on the EventBus. Built-in commands: open_ui, close_ui, switch_panel, set_mode, get_status.

### Memory & Persistence (Long-term Storage)

Two-layer architecture: in-memory cache (`ObjectMemory`) backed by JSON file storage (`JsonStorage`) with atomic writes. Stores spatial objects, tasks, events, and user preferences.

### Context Awareness (Environment)

Detects the user's active application via win32gui, monitors CPU/memory via psutil, and auto-switches modes (developer when VS Code is focused, presentation when PowerPoint is active).

---

## Gesture Reference

| Gesture | Action | Description |
|---------|--------|-------------|
| `Open_Palm` | Toggle UI | Show/hide home menu |
| `Closed_Fist` | Cancel/Close | Cancel action, close UI |
| `Pointing_Up` | Move Cursor | Control cursor via index fingertip |
| `Thumb_Up` | Confirm | Confirm pending action |
| `Thumb_Down` | Reject | Reject pending action |
| `Victory` | Developer Panel | Open developer tools |
| `ILoveYou` | Settings Panel | Open settings |

### Keyboard Hotkeys (brain_main.py)

| Hotkey | Action |
|--------|--------|
| `Ctrl+Space` | Open/close UI |
| `Escape` | Close UI |
| `Ctrl+1/2/3` | Switch panels (System/Developer/Settings) |
| `Tab` | Developer mode |
| `M` | Normal mode |
| `P` | Presentation mode |

---

## Configuration

All settings in `config/desktop.yaml`:

```yaml
camera:
  device_index: 0
  width: 640
  height: 480
  fps_target: 30

model:
  weights: "yolov8n.pt"
  confidence: 0.25

hand_tracking:
  model_path: "models/gesture_recognizer.task"
  num_hands: 2

perception:
  fps_target: 15

spatial:
  object_width_cm: 21.0    # A4 paper width
  object_height_cm: 29.7   # A4 paper height
  focal_length: 640

cursor:
  smoothing: 0.15
  dead_zone: 1
  sensitivity: 2.0
  prediction: 0.12
```

---

## Requirements

- Python 3.12+
- Windows 10/11 (primary target; context detection uses win32gui)
- Webcam (for vision pipeline)
- ~2GB RAM for YOLO + MediaPipe

### Dependencies

| Package | Purpose |
|---------|---------|
| `opencv-python` | Camera capture + frame processing |
| `ultralytics` | YOLOv8 object detection |
| `mediapipe` | Hand tracking + gesture recognition |
| `numpy` | Array operations |
| `PySide6` | Qt overlay UI (brain mode) |
| `dearpygui` | GPU-accelerated dashboard (vision mode) |
| `pynput` | Global hotkey listener |
| `psutil` | CPU/memory monitoring |
| `PyYAML` | Configuration files |

---

## Testing

```bash
pytest -v                                     # All tests
pytest tests/test_gesture_actions.py -v       # Gesture system
pytest tests/test_event_bus.py -v             # EventBus
pytest tests/test_spatial.py -v               # Spatial/PnP
pytest tests/test_database.py -v              # Database storage
pytest tests/test_memory.py -v                # Memory system
```

---

## Documentation

| File | Contents |
|------|----------|
| `docs/ARCHITECTURE.md` | Complete system architecture reference |
| `docs/COMMANDS.md` | Command system framework |
| `docs/EVENTS.md` | EventBus event type reference (69 types) |
| `docs/MEMORY.md` | Memory & persistence architecture |
| `docs/PLUGINS.md` | Plugin development guide |
| `docs/ROADMAP.md` | Development roadmap |
| `docs/API.md` | Public API reference |
| `docs/CONTRIBUTING.md` | Contribution guidelines |

---

## Design Principles

1. **Event-Driven** — No module calls another directly. All communication flows through the EventBus.
2. **Brain-First** — Sensors are input plugins. The intelligence layer is the core.
3. **Multi-Threaded** — Perception runs on background threads. UI stays responsive on the main thread.
4. **Graceful Degradation** — DearPyGui falls back to OpenCV. GestureRecognizer falls back to finger-counting.
5. **Thread-Safe** — All shared state protected by locks. FrameBroker uses Event signaling.
6. **Extensible** — Plugin ABC, Module ABC, Command ABC — add capabilities without modifying core.

---

> **Philosophy**: Sensors are just input plugins — the intelligence layer is the core.
