# Aether Architecture — Backend v1.0.0

## Overview

Aether is a **command-driven operating system** with a unified interaction layer. All input sources (camera, keyboard, CLI, voice) flow through a single pipeline:

```
Input → EventBus → IntentResolver → CommandBus → Handler → ResultPipeline → Output
```

---

## Core Lifecycle

```text
Boot (Application.boot)
  │
  ├─ Load config (vision.yaml)
  ├─ Create ServiceContainer
  ├─ Initialize plugins (order matters)
  ├─ Start camera thread
  └─ Start main loop
       │
       ▼
Tick (30 Hz)
  │
  ├─ CameraPlugin → capture frame → FrameBroker
  ├─ HandPerceptionPlugin (worker thread) → MediaPipe → PerceptionResult
  ├─ ObjectSpatialPlugin (worker thread) → YOLO → PerceptionResult
  ├─ VisionAdapterPlugin (worker thread) → PerceptionResult → EventBus
  ├─ CommandBus.update() → execute queued commands
  ├─ EventBus.flush() → deliver all queued events
  └─ GUIPlugin → render PySide6 overlay
       │
       ▼
Shutdown
  │
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

### PySide6 Overlay
- `OverlayWidget` — main transparent window
- `HUDManager` — manages 4 render layers with throttle
- Widgets read from `OverlayModel` only — stateless renderers
- Per-object QPainterPath caching with hash invalidation

### F1/F2 Toggle
- F1: Toggle object list panel
- F2: Toggle performance HUD

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
| Main | Tick loop, GUI, EventBus flush |
| Camera | Frame capture at 30fps |
| HandPerception | MediaPipe gesture recognition |
| ObjectSpatial | YOLO object detection |
| VisionAdapter | PerceptionResult → EventBus events |
| CLI Reader | stdin readline (non-blocking) |

All threads communicate via EventBus/FrameBroker — no direct cross-thread calls.
