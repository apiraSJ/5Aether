# Aether Architecture — Definitive Reference

> **Project Goal**: Build a modular AI Spatial Assistant that can power a desktop application today and evolve into an XR Smart Glasses assistant in the future.

---

## Table of Contents

1. [Overall Architecture](#overall-architecture)
2. [Data Flow](#data-flow)
3. [Module Reference](#module-reference)
4. [Event Bus](#event-bus)
5. [Pipeline Architecture](#pipeline-architecture)
6. [Gesture System](#gesture-system)
7. [Spatial System](#spatial-system)
8. [Memory & Persistence](#memory--persistence)
9. [Command System](#command-system)
10. [Plugin Architecture](#plugin-architecture)
11. [UI Architecture](#ui-architecture)
12. [Context System](#context-system)
13. [Dual Entry Points](#dual-entry-points)
14. [Performance Budget](#performance-budget)
15. [File Structure](#file-structure)

---

## Overall Architecture

Aether is an **event-driven, multi-threaded system** with two independent operational modes connected by a shared EventBus.

```text
                        ┌─────────────────────────────┐
                        │         AETHER               │
                        │                              │
                        │   ┌─────────────────────┐   │
                        │   │     Event Bus         │   │
                        │   │   (69 Event Types)     │   │
                        │   └──────┬──────┬──────┬──┘   │
                        │          │      │      │       │
                        │     ┌────┘   ┌──┘   ┌──┘      │
                        │     ▼        ▼      ▼          │
                        │  Memory   Tasks  Commands      │
                        │     ▲        ▲      ▲           │
                        │     │        │      │           │
                        │   Json     Json   Handler       │
                        │   Files    Files                │
                        │                              │
                        │   ┌──────────────────────┐   │
                        │   │   Perception Pipeline  │   │
                        │   │  ┌──────┐ ┌────────┐  │   │
                        │   │  │Hand  │ │ YOLO   │  │   │
                        │   │  │Plugin│ │ Plugin │  │   │
                        │   │  └──┬───┘ └───┬────┘  │   │
                        │   │     │          │        │   │
                        │   │  ┌──▼──────────▼──┐    │   │
                        │   │  │  FrameBroker    │    │   │
                        │   │  │  (Thread-safe)  │    │   │
                        │   │  └────────┬───────┘    │   │
                        │   └───────────┼────────────┘   │
                        │               │                │
                        │         ┌─────▼─────┐          │
                        │         │   Camera   │          │
                        │         │  Producer  │          │
                        │         └───────────┘          │
                        └─────────────────────────────┘
```

### Two Entry Points

```text
main.py ─── Camera → FrameBroker → GestureRecognizer + YOLO → DPG Dashboard + Popups
brain_main.py ─── PySide6 Overlay → Hotkeys → Commands → Memory (no camera)
```

Both share the same EventBus, memory, and command systems.

---

## Data Flow

### Vision Pipeline Flow

```text
Camera (30 FPS)
  │
  ├─→ FrameBroker.update_frame()  [producer thread]
  │
  ├─→ HandPerceptionPlugin (daemon thread)
  │     ├─ MediaPipe GestureRecognizer
  │     └─ Emits HAND_DETECTED {landmarks, gesture, gesture_score}
  │
  └─→ ObjectSpatialPlugin (daemon thread)
        ├─ YOLOv8 inference
        ├─ solvePnP distance estimation
        └─ Emits OBJECT_DETECTED {name, confidence, box, distance_z}

EventBus
  ├─→ on_hand_update()  → runtime_hands, runtime_gesture, popup queue
  └─→ on_object_update() → runtime_objects

DearPyGui Render Loop (main thread)
  ├─ Read runtime state (thread-safe lock)
  ├─ Process popup queue → tkinter windows
  ├─ Frame: draw HUD (skeleton, YOLO boxes, cursor, gesture text)
  └─ Render to DPG texture
```

### Brain-Only Flow

```text
pynput (global hotkeys) → EventBus → CommandHandler → execute()
                                            │
                                     ┌──────┼──────┐
                                     ▼      ▼      ▼
                                  Memory  Tasks  UI updates
```

---

## Module Reference

### 1. Core (`core/`)

Application foundation — lifecycle, communication, configuration.

| File | Class / Function | Purpose | Status |
|------|---------|---------|--------|
| `app.py` | `AetherApp` | Top-level lifecycle (init→start→stop→shutdown) | ✅ Complete |
| `event_bus.py` | `EventBus`, `EventType` | Thread-safe pub/sub with 69 event types | ✅ Complete |
| `frame_broker.py` | `FrameBroker` | Thread-safe frame store with Event signaling | ✅ Complete |
| `engine.py` | `AetherEngine` | Core lifecycle + ModuleManager | ✅ Complete |
| `settings.py` | `Settings` | YAML config with deep merge, get/set/save | ✅ Complete |
| `plugin_manager.py` | `PluginManager`, `Plugin` (ABC) | Register/process/shutdown plugins | ✅ Complete |
| `module.py` | `Module` (ABC), `ModuleManager` | Lifecycle interface for brain modules | ✅ Complete |
| `camera.py` | `Camera` | Synchronous OpenCV VideoCapture wrapper | ✅ Complete |
| `camera_thread.py` | `CameraThread` | Threaded capture with Queue | ✅ Complete |
| `detector.py` | `Detector` | YOLOv8 inference wrapper | ✅ Complete |
| `perception_worker.py` | `PerceptionWorker` | Background ML pipeline (throttled) | ✅ Complete |
| `perception_pipeline.py` | `PerceptionPipeline` | Plugin orchestrator per frame | ✅ Complete |
| `renderer.py` | `Renderer` | Draws bounding boxes, 3D axes, labels | ✅ Complete |
| `telemetry.py` | `Telemetry` | FPS estimation via EMA | ✅ Complete |
| `performance.py` | `PerformanceTimer`, `PerformanceTracker` | Block timing + running averages | ✅ Complete |
| `interaction_mode.py` | `InteractionMode`, `InteractionContext` | Mode state machine (PASSIVE→POINTING) | ✅ Complete |
| `logger.py` | `setup_logger()` | Console + file logging | ✅ Complete |

### 2. Perception (`perception/`)

Daemon threads running vision models as independent consumers of FrameBroker.

| File | Class | Model | Emits | Status |
|------|-------|-------|-------|--------|
| `hand_plugin.py` | `HandPerceptionPlugin` | MediaPipe GestureRecognizer | `HAND_DETECTED` (landmarks, gesture, score) | ✅ Complete |
| `object_plugin.py` | `ObjectSpatialPlugin` | YOLOv8 + solvePnP | `OBJECT_DETECTED` (name, box, distance_z) | ✅ Complete |

### 3. Vision (`vision/`)

Computer vision algorithms and data structures.

| File | Class / Function | Purpose | Status |
|------|---------|---------|--------|
| `hand_tracker.py` | `HandTracker`, `HandData`, `HandResults`, `HandLandmark` | MediaPipe HandLandmarker wrapper | ✅ Complete |
| `hand_landmarks.py` | `Landmark` (constants), `HAND_CONNECTIONS` | 21 landmark indices + 20 edges | ✅ Complete |
| `gesture_engine.py` | `GestureEngine`, `GestureEvent` | Rule-based 5-gesture recognizer (fallback) | ✅ Complete |
| `gesture_actions.py` | `GestureType`, `ActionType`, `HandFeatures` | Enums, mapping, finger-counting utilities | ✅ Complete |
| `gesture_executor.py` | `GestureActionExecutor` | Gesture→Action bridge with cooldown | ✅ Complete |
| `command_confirmation.py` | `CommandConfirmation` | Point→Preview→Confirm flow | ✅ Complete |
| `spatial.py` | `SpatialEstimator` | PnP distance estimator | ✅ Complete |
| `calibration.py` | `Calibration` | Camera intrinsics loader | ✅ Complete |
| `pnp.py` | `estimate_pose()` | Standalone solvePnP | ✅ Complete |
| `tracking.py` | `Tracker` | Sequential ID tracker (placeholder) | ⚠️ Placeholder |
| `geometry.py` | `draw_3d_axes()`, `calculate_distance()` | 3D visualization helpers | ✅ Complete |

### 4. UI (`ui/`)

DearPyGui interface for the vision pipeline.

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `dashboard.py` | `Dashboard` | Full DPG window (sidebar, camera, status) 295 lines | ✅ Complete |
| `hand_overlay.py` | `HandOverlay` | Landmark skeleton + cursor crosshair + gesture labels | ✅ Complete |
| `camera_view.py` | `CameraView` | Thin Dashboard wrapper | ✅ Complete |
| `sidebar.py` | `Sidebar` | Section state tracker | ✅ Complete |
| `status_bar.py` | `StatusBar` | FPS/perf status formatting | ✅ Complete |

### 5. Interface (`interface/`)

PySide6 overlay for the brain-only mode.

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `ui.py` | `AetherUI` | Frameless floating overlay, 3 panels, dark theme | ✅ Complete |
| `help_overlay.py` | `HelpOverlay` | Keyboard/gesture reference, auto-hide | ✅ Complete |

### 6. Memory & Database

Two-layer persistence: in-memory cache backed by JSON files.

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `memory/models.py` | `SpatialObject`, `Task`, `EventRecord` | Data models with dict serialization | ✅ Complete |
| `memory/object_memory.py` | `ObjectMemory` | In-memory CRUD cache | ✅ Complete |
| `memory/storage.py` | `MemoryStorage` | User preferences JSON | ✅ Complete |
| `database/storage.py` | `JsonStorage` | Atomic JSON file operations | ✅ Complete |
| `database/objects.py` | `ObjectStore` | Object persistence layer | ✅ Complete |
| `database/tasks.py` | `TaskStore` | Task persistence layer | ✅ Complete |
| `database/events.py` | `EventStore` | Event log persistence | ✅ Complete |

### 7. Tasks (`tasks/`)

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `manager.py` | `TaskManager` | Task lifecycle CRUD | ✅ Complete |

### 8. Commands

Two command frameworks coexist:

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `command/command.py` | `Command` (dataclass), `BaseCommand` (ABC), `CommandRegistry` | Event-driven command system | ✅ Complete |
| `command/handler.py` | `CommandHandler` | Execute + emit events on EventBus | ✅ Complete |
| `commands/base.py` | `Command` (ABC), `CommandResult` | Alternative direct-execution framework | ✅ Complete |
| `commands/__init__.py` | `CommandRegistry` | CLI parse_and_execute | ✅ Complete |
| `commands/remember.py` | `RememberCommand` | Store object in memory | ✅ Complete |
| `commands/find.py` | `FindCommand` | Search by name | ✅ Complete |
| `commands/forget.py` | `ForgetCommand` | Remove by ID | ✅ Complete |
| `commands/list_cmd.py` | `ListCommand` | List all or by status | ✅ Complete |
| `commands/status.py` | `StatusCommand` | Show counts or details | ✅ Complete |
| `commands/task.py` | `TaskCommand` | Create task | ✅ Complete |

### 9. Context (`context/`)

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `context_manager.py` | `ContextManager` | Detects active window (win32gui), CPU/memory | ✅ Complete |

---

## Event Bus

The EventBus is Aether's central nervous system. All modules communicate exclusively through events.

### Architecture

```python
bus = EventBus()  # or get_event_bus() for singleton

# Subscribe
bus.subscribe(EventType.HAND_DETECTED, my_handler)

# Emit
bus.emit(EventType.GESTURE_RECOGNIZED, data={...}, source="gesture_executor")
```

### EventType Categories (69 total)

| Category | Events |
|----------|--------|
| **System** | SYSTEM_STARTUP, SYSTEM_SHUTDOWN, SYSTEM_ERROR, SYSTEM_CONFIG_CHANGED, SYSTEM_RESET, SYSTEM_STANDBY, SYSTEM_WAKE |
| **UI** | UI_OPEN_REQUESTED, UI_CLOSE_REQUESTED, UI_PANEL_SHOW, UI_PANEL_HIDE, UI_THEME_CHANGED, UI_MODE_CHANGED |
| **Input** | INPUT_KEYBOARD, INPUT_MOUSE, INPUT_VOICE, INPUT_GESTURE |
| **Command** | COMMAND_EXECUTE, COMMAND_COMPLETE, COMMAND_FAILED, COMMAND_REGISTERED, COMMAND_UNREGISTERED |
| **Task** | TASK_CREATED, TASK_UPDATED, TASK_COMPLETED, TASK_CANCELLED, TASK_DELETED |
| **Plugin** | PLUGIN_LOADED, PLUGIN_UNLOADED, PLUGIN_ERROR, PLUGIN_STATE_CHANGED |
| **Vision** | OBJECT_DETECTED, HAND_DETECTED, GESTURE_RECOGNIZED, FACE_DETECTED, POSE_DETECTED, ... |
| **Context** | CONTEXT_CHANGED, APP_FOCUS_CHANGED, MODE_CHANGED, ENVIRONMENT_CHANGED |
| **Memory** | MEMORY_OBJECT_ADDED, MEMORY_OBJECT_UPDATED, MEMORY_OBJECT_REMOVED, MEMORY_SEARCHED |
| **Status** | STATUS_HEALTH, STATUS_PERFORMANCE, STATUS_RESOURCE, STATUS_MODEL |

For the complete event list, see `docs/EVENTS.md`.

### Thread Safety

- `subscribe()` / `unsubscribe()` are thread-safe
- `emit()` dispatches synchronously on the caller's thread
- Handlers run on the emitter's thread — use locks for shared state

---

## Pipeline Architecture

### Vision Pipeline (`main.py`)

```text
┌──────────────── Camera Producer (daemon thread) ─────────────────┐
│  cv2.VideoCapture → FrameBroker.update_frame() @ 30 FPS          │
└──────────────────────────┬───────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌─────────────────────┐   ┌──────────────────────────┐
│ HandPerceptionPlugin │   │ ObjectSpatialPlugin       │
│ (daemon thread)      │   │ (daemon thread)           │
│                      │   │                            │
│ GestureRecognizer    │   │ YOLOv8 + solvePnP         │
│ → HAND_DETECTED     │   │ → OBJECT_DETECTED         │
└──────────┬──────────┘   └─────────────┬──────────────┘
           │                            │
           └──────────┬─────────────────┘
                      ▼
            ┌──────────────────┐
            │     EventBus     │
            │  on_hand_update  │
            │ on_object_update │
            └────────┬─────────┘
                     │
                     ▼
            ┌──────────────────┐
            │  DearPyGui Loop  │
            │  (main thread)   │
            │                  │
            │ 1. Read state    │
            │ 2. Draw HUD      │
            │ 3. Render frame  │
            │ 4. Process popups│
            └──────────────────┘
```

### Perception Worker (`core/perception_worker.py`)

An alternative pipeline that runs ML inference throttled at a configurable target FPS (default 15):

```text
Camera → PerceptionPipeline → YOLO Plugin + Hand Plugin
    → SpatialEstimator (PnP distances)
    → GestureEngine + GestureActionExecutor
    → PerceptionSnapshot (thread-safe state)
```

### Multi-Threaded Design

| Thread | Responsibility | FPS |
|--------|---------------|-----|
| Main (DPG render) | UI drawing, popup processing, state read | ~60 |
| Camera producer | FrameBroker feeding | 30 |
| Hand plugin | GestureRecognizer inference | Limited by model |
| Object plugin | YOLOv8 + PnP inference | Limited by model |
| Perception worker | Full pipeline (alt path) | 15 (configurable) |

---

## Gesture System

### Current Model: MediaPipe GestureRecognizer

The primary gesture pipeline uses `models/gesture_recognizer.task` — a MediaPipe model that outputs both **21 hand landmarks** and **gesture classification** natively.

**8 supported gestures**:

| Gesture | Command | Action |
|---------|---------|--------|
| `Closed_Fist` | Cancel / Close | Cancel, close UI |
| `Open_Palm` | Toggle UI | Show/hide dashboard |
| `Pointing_Up` | Move Cursor | Control cursor (via index tip) |
| `Thumb_Up` | Confirm / Accept | Confirm action |
| `Thumb_Down` | Reject / Deny | Reject action |
| `Victory` | Copy / Select | Copy or select |
| `ILoveYou` | Show Help | Display help |
| (none/unknown) | — | — |

### Pipeline

```text
Frame → GestureRecognizer.recognize_for_video() → GestureRecognizerResult
    ├── .hand_landmarks  → 21 landmarks per hand
    ├── .handedness      → Left/Right per hand
    └── .gestures        → [{category_name, score}] per hand
        → HAND_DETECTED event → on_hand_update() → popup queue
```

### Fallback: Rule-Based Engine

The `vision/gesture_engine.py` provides a custom finger-counting fallback (used by brain path):

- Detects 5 gestures: FIST, OPEN_PALM, POINT, THUMBS_UP, THUMB_DOWN
- Uses simple landmark math: `tip.y < pip.y` for extension, `abs(tip.x - mcp.x)` for thumb
- No model dependency — purely geometric

### Popup System

- Each recognized gesture queues a **tkinter popup** showing gesture name + command
- 1.5s cooldown per gesture type prevents spam
- Popups processed on main thread via `_process_popups()` in render loop

---

## Spatial System

### solvePnP Distance Estimation

Objects detected by YOLO are localized in 3D using perspective-n-point:

```text
YOLO bounding box → 4 corners (2D image points)
Object dimensions  → 4 corners (3D world points, default: A4 21×29.7cm)
Camera intrinsics  → focal_length, center_x, center_y (from config)
cv2.solvePnP       → rotation + translation vectors
                    → Z distance in cm
```

### Configuration (`config/desktop.yaml`)

```yaml
spatial:
  object_width_cm: 21.0     # A4 width
  object_height_cm: 29.7    # A4 height
  focal_length: 640          # Approximate focal length (px)
  center_x: 320              # Optical center
  center_y: 240
```

---

## Memory & Persistence

### Architecture

```text
┌──────────────────────────────────────────────┐
│              ObjectMemory (cache)              │
│  add / get / update / remove / search / list   │
└─────────────────────┬────────────────────────┘
                      │ delegates
                      ▼
┌──────────────────────────────────────────────┐
│              ObjectStore                      │
│         JsonStorage CRUD operations           │
└─────────────────────┬────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────┐
│  data/objects.json       (atomic file writes) │
│  data/tasks.json                              │
│  data/events.json                             │
│  data/settings.json                           │
└──────────────────────────────────────────────┘
```

### Data Models

- **SpatialObject**: id, name, label, location(x,y), position_3d, last_seen, status, track_id
- **Task**: id, name, type, status, target_object_id, timestamps, metadata
- **EventRecord**: id, type, timestamp, data

### Storage

`JsonStorage` uses atomic writes (tempfile + shutil.move) to prevent corruption.

---

## Command System

Two command frameworks coexist for different entry points:

### Event-Driven (`command/`)

Used by `brain_main.py` — commands are dataclasses executed via `CommandHandler`:

```python
cmd = Command(name="remember", params={"name": "hammer", "location": (0.5, 0.3)})
handler.execute(cmd)  # → COMMAND_EXECUTE → COMMAND_COMPLETE events
```

### Direct (`commands/`)

Used by CLI — commands are ABC implementations registered in a registry:

```python
registry = CommandRegistry()
registry.register(RememberCommand())
result = registry.parse_and_execute("remember hammer at 0.5 0.3")
```

### Built-in Commands

| Command | What it does |
|---------|-------------|
| `remember <name> at <x> <y>` | Store an object in memory |
| `find <name>` | Search objects by name |
| `forget <id>` | Remove object by ID |
| `list` | List all objects |
| `status` | Show memory stats |
| `task create <name> <type>` | Create a task |

---

## Plugin Architecture

### Plugin ABC

```python
class Plugin(ABC):
    @abstractmethod
    def initialize(self): ...
    @abstractmethod
    def process(self, frame) -> dict: ...
    @abstractmethod
    def shutdown(self): ...
```

### Implementations

| Plugin | Model | Output |
|--------|-------|--------|
| `YoloPlugin` | YOLOv8 | Detections list |
| `HandPlugin` | MediaPipe HandLandmarker | HandResults |

Used by `PerceptionPipeline` to orchestrate multiple vision plugins per frame.

---

## UI Architecture

### DearPyGui Dashboard (`main.py`)

- GPU-accelerated via `add_dynamic_texture` (RGBA float32)
- Manual render loop (`while dpg.is_dearpygui_running() / render_dearpygui_frame()`)
- Left: 640×480 camera feed with HUD overlays
- Right: sidebar with metrics (objects, hands, gesture, command)
- Popup: gesture commands trigger tkinter windows

### PySide6 Overlay (`brain_main.py`)

- Frameless, translucent, always-on-top
- Dark theme with accent colors
- 3 panels: System (CPU/RAM), Developer (tools), Settings (theme, autostart)
- Drag-to-move, auto-resize

### OpenCV Fallback

If DearPyGui fails, `main.py` automatically falls back to `cv2.imshow()`.

---

## Context System

Detects the user's current environment using win32gui:

| Context | Detection | Effect |
|---------|-----------|--------|
| Developer | VS Code, terminals, git windows | Shows developer panel |
| Presentation | PowerPoint, Keynote | Enables presentation mode |
| General | Other applications | Normal mode |

Also monitors CPU and memory usage for the System panel.

---

## Dual Entry Points

### `main.py` — Vision Pipeline

```bash
python main.py
```

- FrameBroker + HandPerceptionPlugin + ObjectSpatialPlugin
- DearPyGui dashboard with OpenCV fallback
- Gesture popup system
- Used when camera is available

### `brain_main.py` — Brain-Only

```bash
python brain_main.py
```

- PySide6 floating overlay
- Global hotkeys (pynput)
- Command system + memory + context
- Gesture bridge for network-received hand data
- Used when no camera is available

### `main_brain.py` — Universal Launcher

```bash
python main_brain.py --mode ui       # PySide6 overlay
python main_brain.py --mode cli      # Interactive shell
python main_brain.py --mode headless # Background daemon
```

---

## Performance Budget

| Model | Input Size | FPS | Latency | Memory |
|-------|-----------|-----|---------|--------|
| MediaPipe GestureRecognizer | 640×480 | 25-35 | 28-40ms | ~20MB |
| YOLOv8n | 640×480 | 8-15 | 65-125ms | ~50MB |
| solvePnP | per-box | 100+ | <1ms | <1MB |
| **Combined** | — | **15-20** | — | **~75MB** |

All inference runs on CPU (no CUDA available on target hardware).

---

## File Structure

```text
Aether/
├── main.py                    # Vision pipeline entry
├── brain_main.py              # Brain-only entry (PySide6)
├── main_brain.py              # Universal launcher
├── config.py                  # Quick YAML loader
├── README.md                  # This file
├── TUTORIALS.md               # Installation & usage
├── requirements.txt           # Dependencies
├── config/
│   ├── desktop.yaml           # Desktop profile
│   └── default.yaml           # Minimal defaults
├── core/
│   ├── app.py                 # AetherApp lifecycle
│   ├── event_bus.py           # EventBus (69 types)
│   ├── frame_broker.py        # Thread-safe frame store
│   ├── engine.py              # AetherEngine
│   ├── camera.py              # Synchronous camera
│   ├── camera_thread.py       # Threaded camera
│   ├── detector.py            # YOLOv8 wrapper
│   ├── perception_worker.py   # Background ML pipeline
│   ├── perception_pipeline.py # Plugin orchestrator
│   ├── plugin_manager.py      # Plugin ABC + registry
│   ├── module.py              # Module ABC + lifecycle
│   ├── settings.py            # YAML config with merge
│   ├── renderer.py            # 2D/3D HUD drawer
│   ├── telemetry.py           # FPS tracking
│   ├── performance.py         # Timing utilities
│   ├── interaction_mode.py    # Mode state machine
│   └── logger.py              # Logging setup
├── perception/
│   ├── hand_plugin.py         # GestureRecognizer daemon
│   └── object_plugin.py       # YOLO+PnP daemon
├── vision/
│   ├── hand_tracker.py        # HandLandmarker wrapper
│   ├── hand_landmarks.py      # 21 landmark constants
│   ├── gesture_engine.py      # Rule-based gesture rec
│   ├── gesture_actions.py     # Enums + HandFeatures
│   ├── gesture_executor.py    # Gesture→Action bridge
│   ├── command_confirmation.py# Point→Preview→Confirm
│   ├── spatial.py             # PnP distance estimator
│   ├── calibration.py         # Camera intrinsics
│   ├── pnp.py                 # Standalone solvePnP
│   ├── tracking.py            # Placeholder tracker
│   └── geometry.py            # 3D helpers
├── ui/
│   ├── dashboard.py           # DPG dashboard
│   ├── camera_view.py         # Camera texture wrapper
│   ├── hand_overlay.py        # Hand skeleton renderer
│   ├── sidebar.py             # Section state
│   └── status_bar.py          # FPS/status strings
├── interface/
│   ├── ui.py                  # PySide6 overlay
│   └── help_overlay.py        # Help reference
├── command/
│   ├── command.py             # Event-driven command system
│   └── handler.py             # CommandHandler
├── commands/
│   ├── __init__.py            # Direct-exec registry
│   ├── base.py                # Command ABC
│   ├── remember.py
│   ├── find.py
│   ├── forget.py
│   ├── list_cmd.py
│   ├── status.py
│   └── task.py
├── memory/
│   ├── models.py              # Data models
│   ├── object_memory.py       # In-memory cache
│   └── storage.py             # User preferences
├── database/
│   ├── storage.py             # Atomic JSON storage
│   ├── objects.py             # ObjectStore
│   ├── tasks.py               # TaskStore
│   └── events.py              # EventStore
├── plugins/
│   ├── yolo_plugin.py         # YOLO as Plugin ABC
│   └── hand_plugin.py         # Hand as Plugin ABC
├── tasks/
│   └── manager.py             # TaskManager
├── context/
│   └── context_manager.py     # Context detection
├── models/
│   ├── gesture_recognizer.task  # MediaPipe model
│   └── hand_landmarker.task     # Legacy landmark model
├── tests/
│   ├── test_aether.py
│   ├── test_gesture_actions.py
│   ├── test_event_bus.py
│   ├── test_database.py
│   ├── test_commands.py
│   ├── test_spatial.py
│   ├── test_perception_worker.py
│   ├── test_memory.py
│   └── test_tasks.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── PLUGINS.md
│   ├── COMMANDS.md
│   ├── MEMORY.md
│   ├── EVENTS.md
│   ├── API.md
│   └── CONTRIBUTING.md
└── logs/
```

---

## Design Principles

1. **Event-Driven**: No module calls another directly. All communication flows through the EventBus.
2. **Brain-First**: Sensors are just input plugins — the intelligence layer is the core.
3. **Multi-Threaded**: Perception runs on background threads, UI stays responsive on the main thread.
4. **Graceful Degradation**: DearPyGui falls back to OpenCV; hand_landmarker falls back to finger-counting.
5. **Thread-Safe**: All shared state protected by locks; FrameBroker uses Event signaling.
6. **Extensible**: Plugin ABC, Module ABC, Command ABC — add new capabilities without modifying core.

---

## Long-Term Vision

```text
Desktop Application
        ↓
Real-Time HUD
        ↓
XR Smart Glasses
        ↓
Spatial AI Assistant
        ↓
Industrial / Military Maintenance Assistant
```
