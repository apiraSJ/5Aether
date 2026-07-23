# Aether Plugin Development Guide

Aether has two plugin systems — one for **perception daemon threads** (primary, used by `main.py`) and one for **batch processing plugins** (alternative, used by `PerceptionPipeline`).

---

## 1. Daemon Thread Perception Plugins (`perception/`)

The primary perception system — independent threads that consume frames from `FrameBroker` and emit events on the `EventBus`.

### Architecture

```text
FrameBroker
    │
    ├─→ HandPerceptionPlugin (daemon thread)
    │     └─→ Emits HAND_DETECTED on EventBus
    │
    └─→ ObjectSpatialPlugin (daemon thread)
          └─→ Emits OBJECT_DETECTED on EventBus
```

### HandPerceptionPlugin

```python
from perception.hand_plugin import HandPerceptionPlugin

plugin = HandPerceptionPlugin(broker, bus, model_path, config)
plugin.start()   # Daemon thread, runs until stop()
# ...
plugin.stop()
```

**Emits**: `EventType.HAND_DETECTED` with:
```python
{
    "hands": [
        {
            "label": "Right",
            "landmarks": [{"x": ..., "y": ..., "z": ...}, ...],  # 21 landmarks
            "gesture": "Closed_Fist",       # MediaPipe native gesture
            "gesture_score": 0.95,
        }
    ]
}
```

### ObjectSpatialPlugin

```python
from perception.object_plugin import ObjectSpatialPlugin

plugin = ObjectSpatialPlugin(broker, bus, model_weight, config)
plugin.start()
```

**Emits**: `EventType.OBJECT_DETECTED` with:
```python
{
    "objects": [
        {
            "name": "person",
            "confidence": 0.88,
            "box": [x1, y1, x2, y2],
            "distance_z": 120.5,  # cm
        }
    ]
}
```

### Creating a Custom Perception Thread

```python
import threading
from core.frame_broker import FrameBroker
from core.event_bus import EventBus, EventType

class MyPerceptionPlugin(threading.Thread):
    def __init__(self, broker: FrameBroker, bus: EventBus, config: dict = None):
        super().__init__(daemon=True)
        self.broker = broker
        self.bus = bus
        self.config = config or {}
        self._running = True
        self._frame_event = self.broker.register_consumer("my_plugin")

    def run(self):
        while self._running:
            self._frame_event.wait(timeout=1.0)
            if not self._running:
                break
            self._frame_event.clear()
            frame = self.broker.get_frame()
            if frame is None:
                continue

            # Process frame
            result = self.process_frame(frame)

            # Emit result on EventBus
            self.bus.emit(EventType.CUSTOM_EVENT, data=result, source="my_plugin")

    def process_frame(self, frame) -> dict:
        # Override with your logic
        return {}

    def stop(self):
        self._running = False
        self._frame_event.set()
        self.join(timeout=2.0)
        self.broker.unregister_consumer("my_plugin")
```

---

## 2. Batch Processing Plugins (`core/plugin_manager.py`)

Alternative plugin interface for frame-by-frame processing through `PerceptionPipeline`.

### Plugin ABC

```python
from core.plugin_manager import Plugin

class MyDetectorPlugin(Plugin):
    @property
    def name(self) -> str:
        return "my_detector"

    def initialize(self, config: dict) -> None:
        self.model = load_my_model()

    def process(self, frame, **kwargs) -> dict:
        detections = self.model(frame)
        return {"my_detections": detections}

    def shutdown(self) -> None:
        del self.model
```

### PluginManager

```python
from core.plugin_manager import PluginManager

manager = PluginManager()

# Register plugins
manager.register(yolo_plugin)
manager.register(hand_plugin)

# Process a frame through all registered plugins
results = manager.process_all(frame)
# results = {"yolo": [...], "hand": HandResults}

# Shutdown all plugins
manager.shutdown_all()
```

### PerceptionPipeline

```python
from core.perception_pipeline import PerceptionPipeline

pipeline = PerceptionPipeline(event_bus, plugin_manager)
result = pipeline.process(frame)
# result.detections — list of object detections
# result.hand_results — HandResults from hand plugin
```

---

## 3. Module System (Brain Path)

The `core/module.py` system is used by `AetherEngine` in the brain-only path.

### Module ABC

```python
from core.module import Module

class MyModule(Module):
    def initialize(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def shutdown(self):
        pass
```

### ModuleManager

```python
from core.module import ModuleManager

manager = ModuleManager()
manager.register("memory", MyMemoryModule())
manager.initialize_all()
manager.start_all()
# ...
manager.stop_all()
manager.shutdown_all()
```

---

## 4. PerceptionWorker (Background ML Pipeline)

An alternative pipeline that runs ML inference throttled at a configurable target FPS:

```text
Camera → PerceptionPipeline → YOLO Plugin + Hand Plugin
    → SpatialEstimator (PnP distances)
    → GestureEngine + GestureActionExecutor
    → PerceptionSnapshot (thread-safe state)
```

```python
from core.perception_worker import PerceptionWorker

worker = PerceptionWorker(broker, event_bus, config)
worker.start()

# Get latest snapshot (thread-safe)
snapshot = worker.get_latest()
# snapshot.detections — list of objects
# snapshot.hands — list of hand observations
# snapshot.gesture — current gesture string

fps = worker.get_fps()
worker.stop()
```

---

## 5. EventBus Integration

All plugins communicate via the central EventBus:

```python
from core.event_bus import EventBus, EventType

bus = EventBus()

# Subscribe to events
bus.subscribe(EventType.HAND_DETECTED, my_handler)

# Emit events (from plugin)
bus.emit(
    EventType.CUSTOM_DETECTED,
    data={"key": "value"},
    source="my_plugin",
)
```

See `docs/EVENTS.md` for the complete event type reference.
