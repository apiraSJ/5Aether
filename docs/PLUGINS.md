# Aether Plugin Development Guide

Aether has two plugin systems — one for **vision perception** (used by the perception pipeline) and one for **brain modules** (used by the engine lifecycle).

---

## 1. Perception Plugin System

### Plugin ABC (`core/plugin_manager.py`)

Vision plugins implement the `Plugin` abstract base class:

```python
from abc import ABC, abstractmethod

class Plugin(ABC):
    @abstractmethod
    def initialize(self):
        """Called once when the plugin is loaded."""
        pass

    @abstractmethod
    def process(self, frame) -> dict:
        """Process a single camera frame. Returns a dict of results.
        
        Args:
            frame: numpy.ndarray, BGR camera frame
            
        Returns:
            dict: Plugin-specific output (e.g., detections, landmarks)
        """
        pass

    @abstractmethod
    def shutdown(self):
        """Called when the plugin is unloaded."""
        pass
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

The pipeline orchestrates plugins per frame:

```python
from core.perception_pipeline import PerceptionPipeline

pipeline = PerceptionPipeline(event_bus, plugin_manager)
result = pipeline.process(frame)
# result.detections — list of object detections
# result.hand_results — HandResults from hand plugin
```

### Example: Custom Object Plugin

```python
from core.plugin_manager import Plugin

class MyDetectorPlugin(Plugin):
    name = "my_detector"

    def initialize(self):
        self.model = load_my_model()

    def process(self, frame):
        detections = self.model(frame)
        return {"my_detections": detections}

    def shutdown(self):
        del self.model
```

### Built-in Plugins

| Plugin | File | Model | Output |
|--------|------|-------|--------|
| `YoloPlugin` | `plugins/yolo_plugin.py` | YOLOv8 (ultralytics) | List of `{box, confidence, class_id, label}` |
| `HandPlugin` | `plugins/hand_plugin.py` | MediaPipe HandLandmarker | `HandResults` with 21 landmarks |

---

## 2. Daemon Thread Plugin System

The `perception/` directory contains higher-level worker threads that consume from `FrameBroker` and emit to `EventBus`. These are the primary perception system used by `main.py`.

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

plugin = ObjectSpatialPlugin(broker, bus, model_path, config)
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

    def run(self):
        while self._running:
            self.broker.new_frame_event.wait(timeout=1.0)
            if not self._running:
                break
            frame = self.broker.get_frame()
            self.broker.clear_event()
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
        self.broker.new_frame_event.set()
        self.join(timeout=2.0)
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

## 4. EventBus Integration

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
