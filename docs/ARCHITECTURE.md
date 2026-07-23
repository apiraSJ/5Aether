# Aether Architecture — Definitive Reference

> **Project Goal**: Build a modular AI Spatial Assistant that powers a desktop application today and evolves into an XR Smart Glasses assistant in the future.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Data Flow](#data-flow)
3. [Module Reference](#module-reference)
4. [EventBus](#eventbus)
5. [Pipeline Architecture](#pipeline-architecture)
6. [Gesture System](#gesture-system)
7. [Spatial System](#spatial-system)
8. [Memory & Persistence](#memory--persistence)
9. [Command System](#command-system)
10. [Plugin Architecture](#plugin-architecture)
11. [UI Architecture](#ui-architecture)
12. [Context System](#context-system)
13. [Interaction System](#interaction-system)
14. [Performance Budget](#performance-budget)
15. [File Structure](#file-structure)

---

## System Overview

Aether is an **event-driven, multi-threaded system** with two independent operational modes connected by a shared EventBus.

```text
                        ┌─────────────────────────────┐
                        │         AETHER               │
                        │                              │
                        │   ┌─────────────────────┐   │
                        │   │     EventBus         │   │
                        │   │  (69 Event Types)    │   │
                        │   └──────┬──────┬──────┬─┘   │
                        │          │      │      │      │
                        │     ┌────┘   ┌──┘   ┌──┘     │
                        │     ▼        ▼      ▼         │
                        │  Memory   Tasks  Commands     │
                        │     ▲        ▲      ▲         │
                        │  Json     Json   Handler      │
                        │  Files    Files               │
                        │                              │
                        │   ┌──────────────────────┐   │
                        │   │  Perception Pipeline   │   │
                        │   │  ┌──────┐ ┌────────┐  │   │
                        │   │  │Hand  │ │ YOLO   │  │   │
                        │   │  │Plug. │ │ Plugin │  │   │
                        │   │  └──┬───┘ └───┬────┘  │   │
                        │   │     │          │       │   │
                        │   │  ┌──▼──────────▼──┐   │   │
                        │   │  │  FrameBroker    │   │   │
                        │   │  │  (Thread-safe)  │   │   │
                        │   │  └────────┬───────┘   │   │
                        │   └───────────┼───────────┘   │
                        │               │               │
                        │         ┌─────▼─────┐         │
                        │         │   Camera   │         │
                        │         │  Producer  │         │
                        │         └───────────┘         │
                        └─────────────────────────────┘
```

### Two Entry Points

```text
main.py ─── Camera → FrameBroker → GestureRecognizer + YOLO → DPG Dashboard + HUD
brain_main.py ─── PySide6 Overlay → Hotkeys → Commands → Memory (no camera)
```

Both share the same EventBus, memory, and command systems.

---

## Data Flow

### Vision Pipeline Flow (`main.py`)

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
  ├─→ GestureRouter.on_hand_update()
  │     ├─ Maps gesture → action with cooldown
  │     ├─ Multi-hand pinch detection (edge-triggered)
  │     └─ Queues actions to ActionQueue
  └─→ GestureRouter.on_object_update()
        └─ Stores runtime objects

ActionQueue (thread-safe bridge)
  ├─→ Cursor update → CursorManager → CursorOverlay (PySide6)
  ├─→ Hover update → UIManager → HomeMenu hover detection
  ├─→ Pinch click → UIManager → menu selection / widget click
  └─→ Deferred EventBus emission → main thread

DearPyGui Render Loop (main thread)
  ├─ processEvents() for PySide6 widgets
  ├─ action_queue.process() — drain queued actions
  ├─ interaction.update() — state machine transitions
  ├─ Get frame from FrameBroker
  ├─ Draw HUD overlays (skeleton, YOLO boxes, cursor, status)
  ├─ Render to DPG texture
  └─ Update metrics display
```

### Brain-Only Flow (`brain_main.py`)

```text
pynput (global hotkeys) → EventBus → CommandHandler → execute()
                                             │
                                      ┌──────┼──────┐
                                      ▼      ▼      ▼
                                   Memory  Tasks  UI updates

Gesture from EventBus → GestureRouter → cursor + menu actions
```

---

## Module Reference

### 1. Core (`core/`)

Application foundation — lifecycle, communication, configuration.

| File | Class / Function | Purpose | Status |
|------|---------|---------|--------|
| `engine.py` | `AetherEngine` | Core lifecycle manager — initialize → start → stop → shutdown modules | Complete |
| `app.py` | `AetherApp` | Top-level owner — owns EventBus, PluginManager, Settings; emits system events | Complete |
| `event_bus.py` | `EventBus`, `EventType`, `Event` | Thread-safe pub/sub with 69 event types, history, singleton accessor | Complete |
| `module.py` | `Module` (ABC), `ModuleManager` | Lifecycle interface (init/start/stop/shutdown) + bulk orchestration | Complete |
| `plugin_manager.py` | `Plugin` (ABC), `PluginManager` | Plugin lifecycle (initialize/process/shutdown) + batch operations | Complete |
| `settings.py` | `Settings` | YAML config with deep merge, hierarchical get/set/save | Complete |
| `frame_broker.py` | `FrameBroker` | Thread-safe frame distribution — producer pushes, each consumer gets its own Event signal | Complete |
| `camera.py` | `Camera` | Synchronous OpenCV VideoCapture wrapper | Complete |
| `camera_thread.py` | `CameraThread` | Threaded capture with bounded Queue, non-blocking `get_frame()` | Complete |
| `detector.py` | `Detector` | Ultralytics YOLOv8 inference wrapper — load, detect, filter confidence | Complete |
| `perception_pipeline.py` | `PerceptionPipeline`, `PerceptionResult` | Orchestrates plugins per frame, collects results into typed object | Complete |
| `perception_worker.py` | `PerceptionWorker`, `PerceptionSnapshot` | Background ML pipeline — YOLO + MediaPipe + gesture + spatial at throttled FPS | Complete |
| `cursor_manager.py` | `CursorManager`, `CursorState` | Camera→screen mapping with contain-mode AR, smoothing, dead-zone, velocity prediction | Complete |
| `gesture_router.py` | `GestureRouter` | Gesture→action routing — cooldown dedup, multi-hand pinch, hold-time gating | Complete |
| `action_queue.py` | `ActionQueue` | Thread-safe queue bridging perception threads → main UI thread, ordered drain | Complete |
| `interaction_mode.py` | `InteractionMode`, `InteractionContext` | Mode state machine (PASSIVE→HOVER→POINTING→CONFIRMING→MENU_OPEN) | Complete |
| `renderer.py` | `Renderer` | OpenCV HUD drawing — bounding boxes, 3D axes, labels, FPS, telemetry | Complete |
| `telemetry.py` | `Telemetry` | Exponentially smoothed FPS + inference/PnP latency + distance metrics | Complete |
| `performance.py` | `PerformanceTimer`, `PerformanceTracker` | Context-manager timing + rolling 100-entry averages | Complete |
| `logger.py` | `setup_logger()` | Console + file logging configuration | Complete |

### 2. Perception (`perception/`)

Daemon threads running ML models as independent consumers of FrameBroker.

| File | Class | Model | Emits | Status |
|------|-------|-------|-------|--------|
| `hand_plugin.py` | `HandPerceptionPlugin` | MediaPipe GestureRecognizer | `HAND_DETECTED` (landmarks, gesture, score) | Complete |
| `object_plugin.py` | `ObjectSpatialPlugin` | YOLOv8 + solvePnP | `OBJECT_DETECTED` (name, box, distance_z) | Complete |

### 3. Vision (`vision/`)

Computer vision algorithms and data structures.

| File | Class / Function | Purpose | Status |
|------|---------|---------|--------|
| `hand_tracker.py` | `HandTracker`, `HandData`, `HandResults`, `HandLandmark` | MediaPipe HandLandmarker wrapper — detect + track 21 landmarks per hand | Complete |
| `hand_landmarks.py` | `Landmark` (constants), `HAND_CONNECTIONS` | 21 landmark indices + 20 skeleton edges + finger tip/pip/mcp indices | Complete |
| `gesture_engine.py` | `GestureEngine`, `GestureEvent` | Rule-based 5-gesture recognizer (fallback) — pure finger-counting math | Complete |
| `gesture_actions.py` | `GestureType`, `ActionType`, `HandFeatures` | Enums, gesture→action mapping, finger extension/pinch/center utilities | Complete |
| `gesture_executor.py` | `GestureActionExecutor` | Gesture→EventBus bridge — cooldown dedup, action mapping | Complete |
| `command_confirmation.py` | `CommandConfirmation` | 2-step confirm flow — POINT→preview→THUMBS_UP confirm / FIST cancel | Complete |
| `spatial.py` | `SpatialEstimator` | PnP distance estimator — bounding box → Z distance in cm | Complete |
| `calibration.py` | `Calibration` | Camera intrinsics loader — YAML file or approximate pinhole fallback | Complete |
| `pnp.py` | `estimate_pose()` | Standalone solvePnP — returns (rvec, tvec) from bounding box | Complete |
| `geometry.py` | `draw_3d_axes()`, `calculate_distance()` | 3D axis projection + Euclidean distance from translation vector | Complete |
| `tracking.py` | `Tracker` | Placeholder — sequential IDs, no real tracking | Placeholder |

### 4. Interface (`interface/`)

PySide6 overlay for brain-only mode and HUD rendering.

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `ui.py` | `AetherUI` | Frameless floating overlay — 3 panels (System/Developer/Settings), dark theme, drag | Complete |
| `ui_manager.py` | `UIManager` | Central controller — owns HomeMenu + StatusBar, routes EventBus events | Complete |
| `home_menu.py` | `HomeMenu` | Gesture-driven vertical chain menu — items with animated sub-panels | Complete |
| `cursor_overlay.py` | `CursorOverlay` | Transparent fullscreen widget — holographic reticle + crosshair (~60 FPS) | Complete |
| `status_bar.py` | `StatusBar` | Top-right overlay — name, HP bar, CPU%, time/date | Complete |
| `hud_renderer.py` | *(standalone functions)* | OpenCV HUD — draw_cursor_on_frame, process_hud_overlays, draw_status_bar | Complete |

### 5. Command System (`command/`)

Event-driven command framework used by brain_main.py.

| File | Class / Function | Purpose | Status |
|------|---------|---------|--------|
| `command.py` | `Command` (dataclass), `BaseCommand` (ABC), `CommandRegistry` | Command abstraction + 5 built-in handlers | Complete |
| `handler.py` | `CommandHandler`, `CommandResult` | Execute + track status (PENDING→EXECUTING→COMPLETED/FAILED) + emit events | Complete |

### 6. Memory & Database

Two-layer persistence: in-memory cache backed by JSON files.

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `memory/models.py` | `SpatialObject`, `Task`, `EventRecord` | Data models with dict serialization | Complete |
| `memory/object_memory.py` | `ObjectMemory` | In-memory CRUD cache — add/get/update/remove/search | Complete |
| `memory/storage.py` | `MemoryStorage` | User preferences — mode, panel, theme, position, activity | Complete |
| `database/storage.py` | `JsonStorage` | Atomic JSON file operations (tempfile + shutil.move) | Complete |
| `database/objects.py` | `ObjectStore` | Object persistence — CRUD + attribute search | Complete |
| `database/tasks.py` | `TaskStore` | Task persistence — CRUD + status filter | Complete |
| `database/events.py` | `EventStore` | Append-only event log — ID generation + retrieval | Complete |

### 7. Tasks (`tasks/`)

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `manager.py` | `TaskManager` | Task lifecycle CRUD — create → start → complete/cancel with timestamps | Complete |

### 8. Context (`context/`)

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `context_manager.py` | `ContextManager` | Detects active window (win32gui), CPU/memory (psutil), auto-mode switching | Complete |

### 9. Interaction (`interaction/`)

| File | Class | Purpose | Status |
|------|-------|---------|--------|
| `interaction_manager.py` | `InteractionManager` | Central coordinator — wires CursorManager + FocusManager + StateMachine + UIManager | Complete |
| `state_machine.py` | `InteractionStateMachine` | FSM — IDLE→TRACKING→MENU_OPEN/PANEL_OPEN with transition handlers | Complete |
| `focus_manager.py` | `FocusManager` | Hit-testing — determines which widget the cursor hovers, dispatches focus/blur/select | Complete |

---

## EventBus

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
| **Menu** | MENU_OPEN, MENU_CLOSE, MENU_ITEM_SELECTED |
| **Status** | STATUS_HEALTH, STATUS_PERFORMANCE, STATUS_RESOURCE, STATUS_MODEL |

### Thread Safety

- `subscribe()` / `unsubscribe()` are thread-safe (use `threading.Lock`)
- `emit()` dispatches synchronously on the caller's thread
- Handlers run on the emitter's thread — use locks for shared state

---

## Pipeline Architecture

### Multi-Threaded Design

| Thread | Responsibility | FPS |
|--------|---------------|-----|
| Main (DPG render) | UI drawing, action processing, state read | ~60 |
| Camera producer | FrameBroker feeding | 30 |
| Hand plugin | GestureRecognizer inference | Limited by model |
| Object plugin | YOLOv8 + PnP inference | Limited by model |
| Perception worker | Full pipeline (alt path) | 15 (configurable) |

### Thread Safety Model

```text
Perception Thread                Main Thread
─────────────────                ───────────
broker.get_frame()               broker.get_frame()
bus.emit(HAND_DETECTED, ...)     action_queue.process()
     │                                │
     └──── ActionQueue.put() ────────►│
              (thread-safe)           ├─→ cursor_manager.update()
                                      ├─→ ui_manager.update_hover()
                                      ├─→ ui_manager.handle_pinch_click()
                                      └─→ bus.emit(deferred events)
```

---

## Gesture System

### Primary: MediaPipe GestureRecognizer

The primary pipeline uses `models/gesture_recognizer.task` — a MediaPipe model that outputs both **21 hand landmarks** and **gesture classification** natively.

**8 supported gestures**:

| Gesture | Command | Action |
|---------|---------|--------|
| `Closed_Fist` | Cancel / Close | Cancel, close UI |
| `Open_Palm` | Toggle UI | Show/hide dashboard |
| `Pointing_Up` | Move Cursor | Control cursor (via index tip) |
| `Thumb_Up` | Confirm / Accept | Confirm action |
| `Thumb_Down` | Reject / Deny | Reject action |
| `Victory` | Developer Panel | Open developer tools |
| `ILoveYou` | Settings Panel | Open settings |
| (none/unknown) | — | — |

### Fallback: Rule-Based Engine

The `vision/gesture_engine.py` provides a custom finger-counting fallback:

- Detects 5 gestures: FIST, OPEN_PALM, POINT, THUMBS_UP, THUMB_DOWN
- Uses simple landmark math: `tip.y < pip.y` for extension
- No model dependency — purely geometric

### Gesture Processing Pipeline

```text
Frame → GestureRecognizer.recognize_for_video() → GestureRecognizerResult
    ├── .hand_landmarks  → 21 landmarks per hand
    ├── .handedness      → Left/Right per hand
    └── .gestures        → [{category_name, score}] per hand
        → HAND_DETECTED event → GestureRouter.on_hand_update()
            ├─ Cooldown dedup (1.5s per gesture type)
            ├─ Hold-time gating on Closed_Fist
            ├─ Multi-hand pinch detection (edge-triggered)
            └─ ActionQueue.put() → main thread processing
```

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

### Event-Driven (`command/`)

Used by `brain_main.py` — commands are dataclasses executed via `CommandHandler`:

```python
cmd = Command(name="open_ui", source="keyboard", params={"panel": "system"})
result = handler.execute(cmd)
# → emits COMMAND_EXECUTE → COMMAND_COMPLETE on EventBus
```

### Built-in Commands

| Command | What it does |
|---------|-------------|
| `open_ui` | Open UI panel |
| `close_ui` | Close UI |
| `switch_panel` | Switch to specified panel |
| `set_mode` | Change interaction mode |
| `get_status` | Get system status |

---

## Plugin Architecture

### Daemon Thread Plugins (`perception/`)

The primary perception system — independent threads consuming from FrameBroker:

```python
class HandPerceptionPlugin(threading.Thread):
    def run(self):
        while self._running:
            self._frame_event.wait(timeout=1.0)
            frame = self.broker.get_frame()
            result = self.recognizer.recognize_for_video(mp_image, timestamp)
            self.bus.emit(EventType.HAND_DETECTED, data={"hands": observations})
```

### Plugin ABC (`core/plugin_manager.py`)

Alternative plugin interface for batch processing:

```python
class Plugin(ABC):
    def initialize(self, config): ...
    def process(self, frame) -> dict: ...
    def shutdown(self): ...
```

---

## UI Architecture

### DearPyGui Dashboard (`main.py`)

- GPU-accelerated via `add_dynamic_texture` (RGBA float32)
- Manual render loop (`while dpg.is_dearpygui_running() / render_dearpygui_frame()`)
- Left: 640×480 camera feed with HUD overlays
- Right: sidebar with metrics (objects, hands, gesture, command)
- OpenCV fallback when DPG fails

### PySide6 Overlay (`brain_main.py`)

- Frameless, translucent, always-on-top
- Dark theme with accent colors
- 3 panels: System (CPU/RAM), Developer (tools), Settings (theme, autostart)
- Gesture-driven HomeMenu with vertical chain layout
- Holographic CursorOverlay with reticle + crosshair
- StatusBar with name, HP bar, CPU%, time

---

## Context System

Detects the user's current environment:

| Context | Detection | Effect |
|---------|-----------|--------|
| Developer | VS Code, terminals, git windows | Shows developer panel |
| Presentation | PowerPoint, Keynote | Enables presentation mode |
| General | Other applications | Normal mode |

Also monitors CPU and memory usage for the System panel.

---

## Interaction System

### State Machine

```text
         ┌─────────────────────────────────┐
         │                                 │
         ▼                                 │
    ┌─────────┐    hand_detected    ┌──────┴──────┐
    │  IDLE   │───────────────────▶│  TRACKING   │
    └─────────┘                    └──────┬──────┘
                                          │
                              menu_open ──┼── menu_close
                                          │
                                 ┌────────▼────────┐
                                 │    MENU_OPEN    │
                                 └────────┬────────┘
                                          │
                              panel_open ─┼── panel_close
                                          │
                                 ┌────────▼────────┐
                                 │    PANEL_OPEN   │
                                 └─────────────────┘
```

### Focus Manager

Hit-testing system that determines which registered widget the virtual cursor is hovering over based on screen-space bounds. Dispatches `on_focus`/`on_blur` on hover changes and `on_select` on pinch-click.

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
├── main.py                     # Vision pipeline entry
├── brain_main.py               # Brain-only entry (PySide6)
├── requirements.txt            # Dependencies
├── config/
│   ├── desktop.yaml            # Desktop profile
│   └── default.yaml            # Minimal defaults
├── core/                       # Application foundation (18 files)
│   ├── engine.py               # AetherEngine lifecycle
│   ├── app.py                  # AetherApp top-level owner
│   ├── event_bus.py            # EventBus (69 types)
│   ├── frame_broker.py         # Thread-safe frame store
│   ├── camera.py / camera_thread.py  # Camera capture
│   ├── detector.py             # YOLOv8 wrapper
│   ├── perception_pipeline.py  # Plugin orchestrator
│   ├── perception_worker.py    # Background ML pipeline
│   ├── cursor_manager.py       # Camera→screen mapping
│   ├── gesture_router.py       # Gesture→action routing
│   ├── action_queue.py         # Thread-safe action bridge
│   ├── interaction_mode.py     # Mode state machine
│   ├── renderer.py             # 2D/3D HUD drawer
│   ├── telemetry.py            # FPS tracking
│   ├── performance.py          # Timing utilities
│   ├── settings.py             # YAML config with merge
│   ├── plugin_manager.py       # Plugin ABC + registry
│   ├── module.py               # Module ABC + lifecycle
│   └── logger.py               # Logging setup
├── perception/                 # Daemon perception threads (2 files)
│   ├── hand_plugin.py          # GestureRecognizer daemon
│   └── object_plugin.py        # YOLO+PnP daemon
├── vision/                     # Computer vision (11 files)
│   ├── hand_tracker.py         # HandLandmarker wrapper
│   ├── hand_landmarks.py       # 21 landmark constants
│   ├── gesture_engine.py       # Rule-based gesture rec
│   ├── gesture_actions.py      # Enums + HandFeatures
│   ├── gesture_executor.py     # Gesture→Action bridge
│   ├── command_confirmation.py # 2-step confirm flow
│   ├── spatial.py              # PnP distance estimator
│   ├── calibration.py          # Camera intrinsics
│   ├── pnp.py                  # Standalone solvePnP
│   ├── geometry.py             # 3D helpers
│   └── tracking.py             # Placeholder tracker
├── interface/                  # PySide6 UI (6 files)
│   ├── ui.py                   # AetherUI overlay
│   ├── ui_manager.py           # UIManager coordinator
│   ├── home_menu.py            # Gesture-driven menu
│   ├── cursor_overlay.py       # Holographic cursor
│   ├── hud_renderer.py         # OpenCV HUD functions
│   └── status_bar.py           # Status overlay
├── command/                    # Command system (2 files)
│   ├── command.py              # Command + Registry
│   └── handler.py              # CommandHandler
├── memory/                     # Memory layer (3 files)
│   ├── models.py               # Data models
│   ├── object_memory.py        # In-memory cache
│   └── storage.py              # User preferences
├── database/                   # Persistence layer (4 files)
│   ├── storage.py              # JsonStorage (atomic)
│   ├── objects.py              # ObjectStore
│   ├── tasks.py                # TaskStore
│   └── events.py               # EventStore
├── tasks/
│   └── manager.py              # TaskManager
├── context/
│   └── context_manager.py      # Context detection
├── interaction/                # UI interaction (3 files)
│   ├── interaction_manager.py  # Central coordinator
│   ├── state_machine.py        # FSM
│   └── focus_manager.py        # Hit-testing
├── models/                     # ML weights
│   ├── gesture_recognizer.task
│   └── hand_landmarker.task
├── tests/                      # pytest (8 files)
└── docs/                       # Documentation (8 files)
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
