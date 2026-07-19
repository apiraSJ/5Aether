# Aether Architecture — Definitive Reference

> **Project Goal**
>
> Build a modular AI Spatial Assistant that can power a desktop application today and evolve into an XR Smart Glasses assistant in the future.

---

## Overall Architecture

```text
                    AETHER

                  Dear PyGui UI
                        │
                        ▼
                  Event Bus (Core)
      ┌────────────┬─────────────┬────────────┐
      ▼            ▼             ▼            ▼
   Memory       Tasks        Commands      Logger
      ▲                            ▲
      │                            │
      └──────────────┬─────────────┘
                     ▼
             Perception Pipeline
      ┌──────────────┼──────────────┐
      ▼              ▼              ▼
 Camera Thread   Hand Plugin    YOLO Plugin
                     │              │
                 MediaPipe      PyTorch
                     │              │
                Hand Events    Object Events
```

---

## Module Reference

### 1. Core — Application Lifecycle

Responsible for starting the application, loading configuration, initializing plugins, managing the Event Bus, and shutting down safely.

**Status**: Planning

**Files**: `core/app.py`

---

### 2. Event Bus ⭐⭐⭐⭐⭐

The communication center. No module calls another directly. Everything flows through events.

```text
HandDetected → Event Bus → Memory → Dashboard → Logger
```

**Benefits**: Independent modules, easy testing, plugin friendly, easy expansion.

**Status**: Not Started

**Files**: `core/event_bus.py`

---

### 3. Camera Thread

Continuously captures camera frames at ~30 FPS. Runs on a separate thread. Only responsible for image acquisition — no AI processing.

**Status**: Not Started

**Files**: `core/camera_thread.py`

---

### 4. Perception Pipeline

Processes camera frames through registered plugins. Produces observations. Never modifies UI directly.

**Status**: Planning

**Files**: `core/perception_pipeline.py`

---

### 5. Hand Tracking

Uses MediaPipe Hand Landmarker. Outputs 21 landmarks, left/right hand, confidence, world coordinates. Produces `HandDetected` events.

**Status**: Research Complete, Implementation Pending

**Files**: `vision/hand_tracker.py`, `plugins/hand_plugin.py`

---

### 6. Gesture Engine

Converts 21 landmarks into recognized gestures: Open Palm, Point, Pinch, Grab, Swipe. Produces `GestureDetected` events.

**Status**: Not Started

**Files**: `vision/gesture_engine.py`

---

### 7. YOLO Plugin

Detects tools, machines, objects, equipment. Produces `ObjectDetected` events.

**Status**: Phase 1 Available, Plugin Integration Pending

**Files**: `core/detector.py`, `plugins/yolo_plugin.py`

---

### 8. Object Memory

Stores remembered objects with spatial data, status, and timestamps. Functions: Remember, Update, Search, Remove.

**Status**: Not Started

**Files**: `memory/object_memory.py`, `memory/models.py`

---

### 9. Task Manager

Manages task lifecycle with states: Pending, Running, Completed, Cancelled.

**Status**: Not Started

**Files**: `tasks/manager.py`

---

### 10. Command System

Executes commands: `remember`, `find`, `forget`, `list`, `status`. Future: voice, gesture, XR menu.

**Status**: Planning

**Files**: `commands/`

---

### 11. Dashboard

Dear PyGui interface showing Camera, HUD, Objects, Tasks, Logs, Status. Same design becomes XR HUD.

**Status**: Planning

**Files**: `ui/dashboard.py`, `ui/camera_view.py`, `ui/hand_overlay.py`, `ui/sidebar.py`, `ui/status_bar.py`

---

## Hybrid Multimodal Architecture

### Fusion Levels

| Level | Description | Aether Usage |
|-------|-------------|--------------|
| **Data-level** | Raw inputs combined before processing | Frame + depth map → RGB-D |
| **Feature-level** | Intermediate features merged | YOLO backbone + MediaPipe embeddings |
| **Decision-level** | Independent results merged | YOLO says "hammer" + MediaPipe says "hand near hammer" → "hand holds hammer" |
| **Temporal** | Frame-to-frame tracking | Object persists across frames even when occluded |

**Aether uses Decision-level + Temporal fusion.**

### Multi-Threaded Pipeline

```text
┌─────────────────────────────────────────────────────────┐
│              PERCEPTION LAYER (Parallel Threads)         │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Camera Thread │  │ YOLO Thread  │  │ MediaPipe    │  │
│  │ (30 FPS)     │  │ (5-15 FPS)   │  │ Hand Thread  │  │
│  │              │  │              │  │ (30 FPS)     │  │
│  │ OpenCV       │  │ ultralytics  │  │ mediapipe    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │ frame           │ detections      │ landmarks │
│         ▼                 ▼                  ▼           │
│  ┌─────────────────────────────────────────────────┐    │
│  │           FUSION ENGINE (Event-Driven)            │    │
│  │                                                   │    │
│  │  Spatial Fusion: hand proximity → "holds object"  │    │
│  │  Temporal Fusion: frame-to-frame persistence      │    │
│  │  Gesture Engine: landmarks → gesture type         │    │
│  │  Command Confirmation: point → preview → execute  │    │
│  └───────────────────────┬───────────────────────────┘    │
│                          │ events                          │
│                          ▼                                 │
│  ┌─────────────────────────────────────────────────┐    │
│  │                   EVENT BUS                       │    │
│  │  ObjectDetected | HandDetected | GestureRecognized│   │
│  └───────────────────────┬───────────────────────────┘    │
│                          │                                 │
│          ┌───────────────┼───────────────┐                │
│          ▼               ▼               ▼                │
│     Memory           Tasks          Dashboard             │
└─────────────────────────────────────────────────────────┘
```

### Performance Budget (CPU Only)

| Model | Input | FPS | Latency | Memory |
|-------|-------|-----|---------|--------|
| YOLOv8n | 640x480 | 8-15 | 65-125ms | ~50MB |
| MediaPipe Hand | 640x480 | 25-35 | 28-40ms | ~20MB |
| PnP Solver | per-object | 100+ | <1ms | <1MB |
| Gesture Classifier | 21 landmarks | 1000+ | <0.1ms | <5MB |
| **Combined** | — | **15-20** | — | **~75MB** |

### Key Code Pattern — Fusion Engine

```python
class FusionEngine:
    def __init__(self, event_bus):
        self.event_bus = event_bus

    def fuse(self, detections, hand_results):
        for hand in hand_results.hands:
            hand_center = self._get_hand_center(hand)
            for det in detections:
                if self._is_inside_box(hand_center, det["box"]):
                    self.event_bus.emit("OBJECT_HELD", {
                        "object": det,
                        "hand": hand.handedness
                    })
```

---

## AI Frameworks

| Framework | Purpose | Status |
|-----------|---------|--------|
| MediaPipe | Hand Tracking | Installed |
| PyTorch | YOLO, Future AI Models | Phase 1 |
| OpenCV | Camera, Drawing, Image Processing | Complete |
| ONNX Runtime | Future Deployment Optimization | Future |
| TF Lite | Future Edge Deployment | Future |

---

## Data Flow

```text
Camera → Camera Thread → Frame Queue → Perception Plugins
    → HandDetected / ObjectDetected → Event Bus
    → Memory / Tasks / Dashboard / Logger
```

---

## Development Progress

### Foundation

```text
Project Setup          ████████████████████ 100%
```

### Core Runtime

```text
Core Runtime           ██░░░░░░░░░░░░░░░░░░ 10%
```

- [ ] App
- [ ] Event Bus
- [ ] Plugin Manager
- [ ] Settings

### Camera System

```text
Camera System          █░░░░░░░░░░░░░░░░░░░ 5%
```

- [ ] Camera Thread
- [ ] Frame Queue

### Hand Tracking

```text
Hand Tracking          █████░░░░░░░░░░░░░░░ 25%
```

- [x] Technology Selected
- [x] MediaPipe Installed
- [x] Landmark Research
- [ ] Plugin
- [ ] Event Output
- [ ] Gesture Recognition

### Object Detection

```text
Object Detection       ████████████████░░░░ 80%
```

- [x] YOLO
- [x] Camera Detection
- [ ] Plugin Integration
- [ ] Event Bus Integration

### Memory, Tasks, Dashboard, Commands

```text
Memory                 ░░░░░░░░░░░░░░░░░░░░ 0%
Tasks                  ░░░░░░░░░░░░░░░░░░░░ 0%
Dashboard              ░░░░░░░░░░░░░░░░░░░░ 0%
Commands               ░░░░░░░░░░░░░░░░░░░░ 0%
```

### Overall

```text
Overall Project        ██████░░░░░░░░░░░░░░ 30%
```

---

## Development Roadmap

### Phase 2.1 — Core

- [x] Event Bus
- [x] App
- [x] Logger
- [x] Settings

### Phase 2.2 — Camera + UI

- [x] Camera Thread
- [x] Frame Queue
- [x] Dear PyGui Window

### Phase 2.3 — Hand Tracking

- [x] MediaPipe Hand Tracking
- [x] Hand Overlay
- [x] HandDetected Events

### Phase 2.4 — Interaction

- [x] Gesture Recognition
- [x] Command System

### Phase 2.5 — Intelligence

- [x] Object Memory
- [x] Task Manager
- [x] Dashboard Panels

### Phase 3 — Integration

- [ ] YOLO Plugin
- [ ] Hand + Object Interaction
- [ ] Smart Glasses HUD

---

## Dependencies

```text
opencv-python>=5.0.0
ultralytics>=8.4.0
numpy>=2.0.0
PyYAML>=6.0
mediapipe>=0.10.14
dearpygui>=1.11.0
psutil>=5.9.0
```

| Package | Status | Purpose |
|---------|--------|---------|
| opencv-python | Installed | Camera, drawing, image processing |
| ultralytics | Installed | YOLOv8 object detection |
| numpy | Installed | Numerical operations |
| PyYAML | Installed | Configuration |
| mediapipe | Not installed | Hand/pose/face landmarks |
| dearpygui | Not installed | Dashboard UI |
| psutil | Installed | System monitoring |

---

## File Structure

```text
Aether/
├── main.py                    # Entry point
├── config.py                  # Configuration loader
├── requirements.txt           # Dependencies
├── config/
│   ├── default.yaml           # Phase 1 defaults
│   └── desktop.yaml           # Desktop profile
├── core/
│   ├── app.py                 # Application lifecycle
│   ├── event_bus.py           # Pub-sub events
│   ├── settings.py            # Profile-based settings
│   ├── camera_thread.py       # Threaded camera capture
│   ├── perception_pipeline.py # Plugin orchestrator
│   ├── plugin_manager.py      # Plugin registration
│   ├── interaction_mode.py    # State machine
│   ├── camera.py              # Phase 1
│   ├── detector.py            # Phase 1
│   ├── renderer.py            # Phase 1
│   ├── telemetry.py           # Phase 1
│   ├── logger.py              # Phase 1
│   └── performance.py         # Phase 1
├── memory/
│   ├── models.py              # SpatialObject, Task, Event
│   └── object_memory.py       # CRUD + search
├── tasks/
│   └── manager.py             # Task lifecycle
├── commands/
│   ├── base.py                # Command base class
│   ├── remember.py
│   ├── find.py
│   ├── forget.py
│   ├── list_cmd.py
│   ├── status.py
│   └── task.py
├── database/
│   ├── storage.py             # JSON file storage
│   ├── objects.py
│   ├── tasks.py
│   └── events.py
├── vision/
│   ├── hand_tracker.py        # MediaPipe wrapper
│   ├── gesture_engine.py      # Gesture recognition
│   ├── command_confirmation.py
│   ├── calibration.py         # Phase 1
│   ├── geometry.py            # Phase 1
│   ├── pnp.py                 # Phase 1
│   └── tracking.py            # Phase 1
├── ui/
│   ├── dashboard.py           # Dear PyGui main window
│   ├── camera_view.py         # Camera texture
│   ├── hand_overlay.py        # Landmark + menu viz
│   ├── sidebar.py             # Navigation
│   └── status_bar.py          # FPS / latency
├── plugins/
│   ├── yolo_plugin.py         # YOLO perception plugin
│   └── hand_plugin.py         # Hand tracking plugin
├── models/
│   ├── yolov8n.pt
│   └── hand_landmarker.task
├── tests/
│   ├── test_aether.py
│   ├── test_event_bus.py
│   ├── test_memory.py
│   ├── test_tasks.py
│   ├── test_commands.py
│   └── test_database.py
├── logs/
├── assets/
└── docs/
    └── ARCHITECTURE.md
```

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
