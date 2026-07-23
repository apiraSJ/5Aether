# Aether API Reference

> Developer reference for Aether's public APIs.

---

## EventBus

### `core.event_bus`

```python
from core.event_bus import EventBus, EventType, Event, get_event_bus

# Singleton access
bus = get_event_bus()

# Subscribe / unsubscribe
handler_id = bus.subscribe(EventType.HAND_DETECTED, callback)
bus.unsubscribe(EventType.HAND_DETECTED, callback)
bus.unsubscribe(handler_id)

# Emit
bus.emit(EventType.GESTURE_RECOGNIZED, data={...}, source="module_name")
bus.emit_simple(EventType.MENU_OPEN, {})

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
- `INPUT_*` — keyboard, mouse, voice, gesture, hotkey
- `COMMAND_*` — execute, complete, failed, registered
- `TASK_*` — created, updated, completed, cancelled
- `PLUGIN_*` — loaded, unloaded, error
- `VISION_*` — object/hand/gesture/face/pose detected
- `CONTEXT_*` — context/app/mode/environment changed
- `MEMORY_*` — object added/updated/removed/searched
- `MENU_*` — open, close, item selected
- `STATUS_*` — health, performance, resource

See `docs/EVENTS.md` for the full list.

---

## FrameBroker

### `core.frame_broker`

```python
from core.frame_broker import FrameBroker

broker = FrameBroker()

# Producer (camera thread)
broker.update_frame(frame)     # Store frame + signal all consumers

# Consumer (perception threads) — per-consumer Event
frame_event = broker.register_consumer("my_consumer")
frame_event.wait(timeout=1.0)  # Block until new frame
frame = broker.get_frame()     # Get latest frame (non-blocking)
frame_event.clear()            # Reset after consuming

# Cleanup
broker.unregister_consumer("my_consumer")
```

---

## Gesture System

### `vision.gesture_actions`

```python
from vision.gesture_actions import (
    GestureType,          # Enum: FIST, OPEN_PALM, POINT, THUMBS_UP, THUMB_DOWN, UNKNOWN
    ActionType,           # Enum: TOGGLE_UI, MOVE_CURSOR, CLICK, CONFIRM, CANCEL, NO_ACTION
    GestureAction,        # Dataclass: action, gesture, position, confidence, timestamp
    HandFeatures,         # Static methods for finger analysis
    DEFAULT_GESTURE_MAP,  # Dict[GestureType, ActionType]
    GESTURE_COMMAND_NAMES,# Dict[GestureType, str]
)

# Finger counting
lm = hand_landmarks
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

tracker = HandTracker(config={"model_path": "models/hand_landmarker.task"})
tracker.initialize()
results = tracker.process(frame_bgr)
# results.hands — list of HandData
# results.timestamp_ms

# HandData fields:
#   .landmarks — list of 21 HandLandmark (x, y, z)
#   .world_landmarks — 3D world coordinates
#   .handedness — "Left" or "Right"
#   .confidence — detection confidence
#   .bounding_box — (x1, y1, x2, y2)
tracker.shutdown()
```

### `vision.hand_landmarks`

```python
from vision.hand_landmarks import Landmark, HAND_CONNECTIONS, FINGER_TIPS

Landmark.WRIST              # 0
Landmark.THUMB_TIP          # 4
Landmark.INDEX_FINGER_TIP   # 8
# ... 21 constants

HAND_CONNECTIONS  # list of (a, b) tuples — 20 bone connections
FINGER_TIPS       # [4, 8, 12, 16, 20] — tip indices
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

### `vision.calibration`

```python
from vision.calibration import Calibration

calib = Calibration(width=640, height=480)
camera_matrix = calib.camera_matrix
dist_coeffs = calib.dist_coeffs
# Loads from YAML if available, otherwise approximates
```

---

## Command System

### Event-Driven (`command/`)

```python
from command.command import Command, CommandRegistry, create_default_registry, create_command
from command.handler import CommandHandler, CommandResult

# Create a command
cmd = Command(name="open_ui", params={"panel": "system"}, source="keyboard")
cmd = create_command("open_ui", source="keyboard", panel="system")

# Execute
handler = CommandHandler(event_bus)
result = handler.execute(cmd)
# result.success — bool
# result.message — str
# result.data — Any

# Registry
registry = create_default_registry()
handler.register_commands(registry)
```

---

## Memory System

### `memory.object_memory`

```python
from memory.object_memory import ObjectMemory

memory = ObjectMemory(object_store)

# CRUD
obj = memory.add(name="hammer", location=(0.5, 0.3), label="tool")
memory.update(obj.id, status="active")
memory.remove(obj.id)
obj = memory.get(obj.id)

# Search
results = memory.search_by_name("hammer")
results = memory.get_by_location(x=0.5, y=0.3, tolerance=0.1)

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

### `memory.storage`

```python
from memory.storage import MemoryStorage

prefs = MemoryStorage("data/settings.json")
prefs.set("mode", "developer")
prefs.set("last_panel", "system")
value = prefs.get("mode")
prefs.add_activity("startup")
memory = prefs.get_memory()
```

---

## Task System

### `tasks.manager`

```python
from tasks.manager import TaskManager

manager = TaskManager(task_store)
task = manager.create(name="Find hammer", type="search")
manager.update_status(task.id, "running")   # Sets started_at
manager.complete(task.id)                    # Sets completed_at
manager.cancel(task.id)
manager.remove(task.id)

tasks = manager.list_all()
pending = manager.list_by_status("pending")
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
all_data = store.all()
store.clear()
```

### `database.objects`

```python
from database.objects import ObjectStore

obj_store = ObjectStore(JsonStorage("data/objects.json"))
obj_store.save(obj_dict)
obj_dict = obj_store.load("obj_001")
obj_store.delete("obj_001")
all = obj_store.list_all()
results = obj_store.search(name="hammer")
```

### `database.tasks`

```python
from database.tasks import TaskStore

task_store = TaskStore(JsonStorage("data/tasks.json"))
task_store.save(task_dict)
pending = task_store.list_by_status("pending")
all = task_store.list_all()
```

### `database.events`

```python
from database.events import EventStore

event_store = EventStore(JsonStorage("data/events.json"))
event_store.log("object_detected", {"id": "obj_001"})
recent = event_store.get_recent(10)
by_type = event_store.get_by_type("hand_detected")
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

### `perception.hand_plugin`

```python
from perception.hand_plugin import HandPerceptionPlugin

plugin = HandPerceptionPlugin(
    broker=broker,
    bus=event_bus,
    model_path="models/gesture_recognizer.task",
    config={"num_hands": 2},
)
plugin.start()
# Emits HAND_DETECTED events on EventBus
plugin.stop()
```

### `perception.object_plugin`

```python
from perception.object_plugin import ObjectSpatialPlugin

plugin = ObjectSpatialPlugin(
    broker=broker,
    bus=event_bus,
    model_weight="yolov8n.pt",
    config={"confidence": 0.25},
)
plugin.start()
# Emits OBJECT_DETECTED events on EventBus
plugin.stop()
```

---

## Context

### `context.context_manager`

```python
from context.context_manager import ContextManager

ctx = ContextManager()
ctx.update(active_app="Code.exe", active_window="main.py")
mode = ctx.get_mode()           # → "developer" / "presentation" / "normal"
ctx.set_mode("developer")
context = ctx.get_context()     # → ContextSnapshot
summary = ctx.get_summary()     # → dict with all context info
history = ctx.get_history(10)   # → list of recent snapshots
```

---

## Interaction

### `interaction.interaction_manager`

```python
from interaction.interaction_manager import InteractionManager

manager = InteractionManager(cursor_manager, ui_manager, event_bus)
manager.update()  # Call each frame
```

### `interaction.state_machine`

```python
from interaction.state_machine import InteractionStateMachine, InteractionState

fsm = InteractionStateMachine()
fsm.on("transition", callback)
fsm.hand_detected()    # IDLE → TRACKING
fsm.menu_opened()      # TRACKING → MENU_OPEN
fsm.menu_closed()      # MENU_OPEN → TRACKING
fsm.hand_lost()        # TRACKING → IDLE
current = fsm.current   # → InteractionState
```

### `interaction.focus_manager`

```python
from interaction.focus_manager import FocusManager

fm = FocusManager()
fm.register("button1", x=100, y=200, width=80, height=40,
            on_focus=lambda: print("focused"),
            on_blur=lambda: print("blurred"),
            on_select=lambda: print("selected"))
fm.update(cursor_x=120, cursor_y=210)  # Hit test
fm.select()                             # Trigger on_select if focused
```

---

## Cursor Manager

### `core.cursor_manager`

```python
from core.cursor_manager import CursorManager

cm = CursorManager()
cm.update(hand_x=0.5, hand_y=0.3, gesture="Pointing_Up",
          gesture_score=0.95, is_pinch=False)
state = cm.get_state()
# state.screen_x, state.screen_y — screen coordinates
# state.is_pinch — bool
# state.gesture — str
# state.is_visible — bool
cm.hide()
cm.show()
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

engine = create_engine(config)
engine.initialize()
engine.start()
# ...
engine.stop()
engine.shutdown()
status = engine.get_status()
```

---

## Interface (PySide6)

### `interface.ui`

```python
from interface.ui import AetherUI, create_system_panel, create_developer_panel, create_settings_panel

ui = AetherUI(context_manager=ctx, memory_storage=memory)
ui.register_panel("system", "SYSTEM", create_system_panel(ctx))
ui.show_panel("system")
ui.set_mode("developer")
ui.show()
```

### `interface.ui_manager`

```python
from interface.ui_manager import UIManager

mgr = UIManager(cursor_manager, event_bus)
mgr.show()
mgr.update_hover()
action = mgr.handle_pinch_click()
```

### `interface.home_menu`

```python
from interface.home_menu import HomeMenu

menu = HomeMenu(parent=None)
menu.show_at(x=100, y=200)
menu.hide_menu()
menu.update_hover(cursor_x=120, cursor_y=250)
item = menu.select_hovered()
```

### `interface.cursor_overlay`

```python
from interface.cursor_overlay import CursorOverlay

overlay = CursorOverlay(cursor_manager)
overlay.show()
# Automatically renders at ~60 FPS via QTimer
```

### `interface.hud_renderer`

```python
from interface.hud_renderer import (
    process_hud_overlays,
    draw_cursor_on_frame,
    draw_status_bar,
    draw_pinch_line,
)

processed = process_hud_overlays(frame, hands, objects, mirror=True)
draw_cursor_on_frame(frame, x, y, is_pinch, gesture, mirror=True)
draw_status_bar(frame, gesture, is_pinch, hand_count)
```
