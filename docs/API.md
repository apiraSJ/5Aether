# Aether API Reference

> Developer reference for Aether's public APIs.

---

## EventBus

### `core.event_bus`

```python
from core.event_bus import EventBus, EventType, Event

# Singleton access
bus = get_event_bus()

# Subscribe / unsubscribe
handler_id = bus.subscribe(EventType.HAND_DETECTED, callback)
bus.unsubscribe(EventType.HAND_DETECTED, callback)
bus.unsubscribe(handler_id)

# Emit
bus.emit(EventType.GESTURE_RECOGNIZED, data={...}, source="module_name")

# History
recent = bus.get_history(count=10)
filtered = bus.get_history(event_type=EventType.HAND_DETECTED)

# Utility
bus.subscriber_count(EventType.HAND_DETECTED)  # → int
```

### `Event` dataclass

```python
@dataclass
class Event:
    type: EventType
    data: dict
    source: str
    timestamp: float
    event_id: str
```

### `EventType` Enum (69 types)

Categories:
- `SYSTEM_*` — startup, shutdown, error, config
- `UI_*` — open/close, panel show/hide, theme, mode
- `INPUT_*` — keyboard, mouse, voice, gesture
- `COMMAND_*` — execute, complete, failed, registered
- `TASK_*` — created, updated, completed, cancelled
- `PLUGIN_*` — loaded, unloaded, error
- `VISION_*` — object/hand/gesture/face/pose detected
- `CONTEXT_*` — context/app/mode/environment changed
- `MEMORY_*` — object added/updated/removed/searched
- `STATUS_*` — health, performance, resource

See `docs/EVENTS.md` for the full list.

---

## FrameBroker

### `core.frame_broker`

```python
from core.frame_broker import FrameBroker

broker = FrameBroker()

# Producer (camera thread)
broker.update_frame(frame)     # Store frame + set event

# Consumer (perception threads)
broker.new_frame_event.wait()  # Block until new frame
frame = broker.get_frame()     # Get latest frame (non-blocking)
broker.clear_event()           # Reset event after consuming

# Deconstructor
frame = broker.get_frame()     # Same as get_frame() + deque
```

---

## Gesture System

### `vision.gesture_actions`

```python
from vision.gesture_actions import (
    GestureType,        # Enum: FIST, OPEN_PALM, POINT, THUMBS_UP, THUMB_DOWN, UNKNOWN
    ActionType,         # Enum: TOGGLE_UI, MOVE_CURSOR, CLICK, CONFIRM, CANCEL, NO_ACTION
    GestureAction,      # Dataclass: action, gesture, position, confidence, timestamp
    HandFeatures,       # Static methods: is_finger_extended, count_extended, pinch_distance, etc.
    DEFAULT_GESTURE_MAP,  # Dict[GestureType, ActionType]
    GESTURE_COMMAND_NAMES, # Dict[GestureType, str]
)

# Finger counting
lm = hand.landmarks
extended = HandFeatures.count_extended(lm)
is_index_up = HandFeatures.is_finger_extended(lm, "index")
distance = HandFeatures.pinch_distance(lm)
center = HandFeatures.hand_center(lm)
tip_pos = HandFeatures.index_tip_position(lm)
```

### `vision.gesture_engine`

```python
from vision.gesture_engine import GestureEngine, GestureEvent

engine = GestureEngine(config={})
events = engine.update(hand_results)  # Returns list of GestureEvent
cx, cy = engine.get_cursor_position()
```

### `vision.gesture_executor`

```python
from vision.gesture_executor import GestureActionExecutor

executor = GestureActionExecutor(event_bus, gesture_engine)
actions = executor.process_events(gesture_events)  # Returns list of GestureAction
cursor = executor.get_cursor()  # → (x, y)
```

---

## Hand Tracking

### `vision.hand_tracker`

```python
from vision.hand_tracker import HandTracker, HandData, HandResults, HandLandmark

tracker = HandTracker(model_path="models/hand_landmarker.task")
results = tracker.process(frame_bgr)
# results.hands — list of HandData
# results.timestamp_ms

# HandData fields:
#   .landmarks — list of 21 HandLandmark (x, y, z)
#   .world_landmarks — 3D world coordinates
#   .handedness — "Left" or "Right"
#   .confidence — detection confidence
#   .bounding_box — (x1, y1, x2, y2)
```

### `vision.hand_landmarks`

```python
from vision.hand_landmarks import Landmark, HAND_CONNECTIONS

Landmark.WRIST          # 0
Landmark.THUMB_TIP      # 4
Landmark.INDEX_FINGER_TIP  # 8
# ... 21 constants

# 20 bone connections for drawing skeleton
HAND_CONNECTIONS  # list of (a, b) tuples
```

---

## Spatial & PnP

### `vision.spatial`

```python
from vision.spatial import SpatialEstimator

estimator = SpatialEstimator(config={
    "object_width_cm": 21.0,
    "object_height_cm": 29.7,
    "focal_length": 640,
    "center_x": 320,
    "center_y": 240,
})
distance_cm = estimator.estimate(box=(x1, y1, x2, y2))
# Returns float (cm) or None
```

### `vision.pnp`

```python
from vision.pnp import estimate_pose

rvec, tvec = estimate_pose(box, camera_matrix, dist_coeffs)
```

### `vision.geometry`

```python
from vision.geometry import draw_3d_axes, calculate_distance

frame = draw_3d_axes(frame, camera_matrix, rvec, tvec)
distance = calculate_distance(tvec)  # L2 norm
```

---

## Plugin System

### `core.plugin_manager`

```python
from core.plugin_manager import PluginManager, Plugin

class MyPlugin(Plugin):
    name = "my_plugin"

    def initialize(self):
        pass

    def process(self, frame) -> dict:
        return {"result": ...}

    def shutdown(self):
        pass

manager = PluginManager()
manager.register(MyPlugin())
results = manager.process_all(frame)  # → {"my_plugin": {...}}
manager.shutdown_all()
```

---

## Command System

### Event-Driven (`command/`)

```python
from command.command import Command, CommandRegistry, create_default_registry
from command.handler import CommandHandler

# Create and execute a command
cmd = Command(name="remember", params={"name": "hammer", "location": (0.5, 0.3)})
handler = CommandHandler(event_bus)
result = handler.execute(cmd)
```

### Direct-Execution (`commands/`)

```python
from commands import CommandRegistry

registry = CommandRegistry()
registry.register(RememberCommand())
result = registry.parse_and_execute("remember hammer at 0.5 0.3")
```

---

## Memory System

### `memory.object_memory`

```python
from memory.object_memory import ObjectMemory
from memory.models import SpatialObject

memory = ObjectMemory(object_store)

# CRUD
obj = memory.add("hammer", location=(0.5, 0.3), label="tool")
memory.update(obj.id, status="active")
memory.remove(obj.id)
obj = memory.get(obj.id)

# Search
results = memory.search_by_name("hammer")
results = memory.get_by_location(x=0.5, y=0.3)

# Listing
all_objects = memory.list_all()
count = memory.count
```

### `memory.models`

```python
from memory.models import SpatialObject, Task, EventRecord

obj = SpatialObject(
    id=..., name="hammer", label="tool",
    location=(0.5, 0.3), position_3d=(0.0, 0.0, 1.2),
    last_seen=..., status="active",
)
obj.to_dict()  # → dict
SpatialObject.from_dict(d)  # → SpatialObject
```

---

## Task System

### `tasks.manager`

```python
from tasks.manager import TaskManager

manager = TaskManager(task_store)
task = manager.create_task("Find hammer", "search")
manager.update_status(task.id, "running")
manager.complete_task(task.id)
manager.cancel_task(task.id)
manager.remove_task(task.id)

tasks = manager.list_by_status("pending")
```

---

## Database

### `database.storage`

```python
from database.storage import JsonStorage

store = JsonStorage("data/objects.json")
store.set("key", value)
value = store.get("key")
store.delete("key")
keys = store.keys()
store.clear()
```

---

## Settings

### `core.settings`

```python
from core.settings import Settings

settings = Settings("config/desktop.yaml")
value = settings.get("camera.device_index")
settings.set("camera.device_index", 1)
settings.save()
```

All keys and defaults are in `settings.py` `DEFAULT_SETTINGS`.

---

## Perception Threads

### `perception/hand_plugin.py`

```python
from perception.hand_plugin import HandPerceptionPlugin

plugin = HandPerceptionPlugin(
    broker=broker,
    bus=bus,
    model_path="models/gesture_recognizer.task",
    config={"num_hands": 2},
)
plugin.start()
# ...
plugin.stop()
```

### `perception/object_plugin.py`

```python
from perception.object_plugin import ObjectSpatialPlugin

plugin = ObjectSpatialPlugin(
    broker=broker,
    bus=bus,
    model_path="yolov8n.pt",
    config={"confidence": 0.25},
)
plugin.start()
# ...
plugin.stop()
```

---

## Context

### `context.context_manager`

```python
from context.context_manager import ContextManager

ctx = ContextManager()
snapshot = ctx.get_current_context()
# → {"mode": "developer", "active_app": "Code.exe",
#     "cpu_percent": 45.0, "memory_percent": 62.3, ...}
```

---

## UI

### `ui.dashboard`

```python
from ui.dashboard import Dashboard

dashboard = Dashboard(event_bus)
dashboard.run()  # Blocking DPG render loop
```

### `ui.hand_overlay`

```python
from ui.hand_overlay import HandOverlay

overlay = HandOverlay()
frame = overlay.draw_landmarks(frame, landmarks)
frame = overlay.draw_cursor(frame, x, y, gesture)
frame = overlay.draw_gesture_label(frame, gesture, action)
```

### `interface.ui`

```python
from interface.ui import run_aether_ui

run_aether_ui(event_bus, engine, memory, context)
# Starts PySide6 event loop (blocking)
```

---

## Application Lifecycle

### `core.app`

```python
from core.app import AetherApp

app = AetherApp("config/desktop.yaml")
app.initialize()
# ... use event_bus, settings, plugin_manager ...
app.shutdown()
```

### `core.engine`

```python
from core.engine import AetherEngine, create_engine

engine = create_engine()
engine.initialize()
engine.start()
# ...
engine.stop()
engine.shutdown()
```
