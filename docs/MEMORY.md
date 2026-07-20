# Aether Memory System Reference

Aether uses a two-layer memory architecture: an **in-memory cache** for fast access backed by **JSON file storage** for persistence.

---

## Architecture

```text
┌───────────────────────────────────────────┐
│            ObjectMemory (cache)            │
│  add / get / update / remove / search      │
│  list_all / get_by_location / count        │
└───────────────────┬───────────────────────┘
                    │ delegates
                    ▼
┌───────────────────────────────────────────┐
│            ObjectStore                     │
│  JsonStorage CRUD with search filtering    │
└───────────────────┬───────────────────────┘
                    │
                    ▼
┌───────────────────────────────────────────┐
│   data/objects.json  (atomic file writes)  │
└───────────────────────────────────────────┘
```

---

## Data Models

### SpatialObject

```python
from memory.models import SpatialObject

obj = SpatialObject(
    id="obj_001",                 # Unique identifier
    name="hammer",                # Display name
    label="tool",                 # Category label
    location=(0.5, 0.3),          # 2D normalized position (x, y)
    position_3d=(0.0, 0.0, 1.2), # 3D position in meters (x, y, z)
    last_seen=datetime.now(),     # Last observation timestamp
    status="active",              # active, inactive, archived
    track_id=42,                  # Tracking ID (optional)
    metadata={"color": "red"},    # Arbitrary key-value store
)

# Serialization
d = obj.to_dict()
obj2 = SpatialObject.from_dict(d)
```

### Task

```python
from memory.models import Task

task = Task(
    id="task_001",
    name="Find the hammer",
    type="search",
    status="pending",     # pending → running → completed / cancelled
    target_object_id="obj_001",
    created_at=datetime.now(),
    started_at=None,
    completed_at=None,
    metadata={},
)
```

### EventRecord

```python
from memory.models import EventRecord

event = EventRecord(
    id="evt_001",
    type="object_detected",
    timestamp=datetime.now(),
    data={"object_id": "obj_001", "confidence": 0.95},
)
```

---

## ObjectMemory API

```python
from memory.object_memory import ObjectMemory

memory = ObjectMemory(object_store)

# CRUD
obj = memory.add(name="hammer", location=(0.5, 0.3), label="tool")
obj = memory.get("obj_001")
memory.update("obj_001", status="active")
memory.remove("obj_001")

# Search
results = memory.search_by_name("ham")    # Case-insensitive substring
results = memory.get_by_location(x=0.5, y=0.3, tolerance=0.1)

# Listing
all = memory.list_all()
count = memory.count
```

---

## Storage Layer

### JsonStorage

```python
from database.storage import JsonStorage

store = JsonStorage("data/objects.json")
store.set("key", {"nested": "value"})
value = store.get("key")          # → {"nested": "value"}
store.delete("key")
keys = store.keys()               # → ["key", ...]
all = store.all()                 # → {"key": value, ...}
store.clear()
```

Uses atomic writes (write to temp file, then `shutil.move`) to prevent data corruption.

### ObjectStore

```python
from database.objects import ObjectStore

object_store = ObjectStore(JsonStorage("data/objects.json"))
object_store.save(obj_dict)
obj_dict = object_store.load("obj_001")
object_store.delete("obj_001")
all = object_store.list_all()
```

### TaskStore / EventStore

```python
from database.tasks import TaskStore
from database.events import EventStore

task_store = TaskStore(JsonStorage("data/tasks.json"))
pending = task_store.list_by_status("pending")

event_store = EventStore(JsonStorage("data/events.json"))
event_store.log("object_detected", {"id": "obj_001"})
recent = event_store.get_recent(10)
```

---

## MemoryStorage (User Preferences)

```python
from memory.storage import MemoryStorage

prefs = MemoryStorage("data/settings.json")
prefs.set("mode", "developer")
prefs.set("last_panel", "system")
prefs.set("theme", "dark")
prefs.add_activity("startup")
```

Stores: mode, last_panel, theme, ui_position, user_preferences, recent_activity.

---

## EventBus Integration

Memory operations emit events on the EventBus:

| Event | When |
|-------|------|
| `MEMORY_OBJECT_ADDED` | Object added to memory |
| `MEMORY_OBJECT_UPDATED` | Object metadata changed |
| `MEMORY_OBJECT_REMOVED` | Object deleted |
| `MEMORY_SEARCHED` | Search executed |
| `TASK_CREATED` | Task created |
| `TASK_UPDATED` | Task status changed |
| `TASK_COMPLETED` | Task completed |
| `TASK_CANCELLED` | Task cancelled |
