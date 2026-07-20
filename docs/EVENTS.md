# Aether EventBus Reference

The EventBus is Aether's central communication system. All modules communicate exclusively through events — no direct coupling.

---

## Usage

```python
from core.event_bus import EventBus, EventType, Event, get_event_bus

# Get the singleton
bus = get_event_bus()

# Subscribe to events
handler_id = bus.subscribe(EventType.HAND_DETECTED, my_handler)

# Unsubscribe (by handler or by ID)
bus.unsubscribe(EventType.HAND_DETECTED, my_handler)
bus.unsubscribe(handler_id)

# Emit an event
bus.emit(
    EventType.GESTURE_RECOGNIZED,
    data={"gesture": "Open_Palm", "confidence": 0.95},
    source="gesture_executor",
)

# Get history
recent = bus.get_history(count=10)
filtered = bus.get_history(event_type=EventType.HAND_DETECTED)

# Check subscriber count
bus.subscriber_count(EventType.HAND_DETECTED)
```

## Event Dataclass

```python
@dataclass
class Event:
    type: EventType       # Enum member
    data: dict            # Event payload
    source: str           # Module that emitted the event
    timestamp: float      # Emit time (time.time())
    event_id: str         # Unique ID (str(uuid4()))
```

---

## EventType Reference (69 Types)

### System Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `SYSTEM_STARTUP` | `{version, config}` | `AetherApp.initialize()` |
| `SYSTEM_SHUTDOWN` | `{uptime}` | `AetherApp.shutdown()` |
| `SYSTEM_ERROR` | `{error, traceback}` | Any module |
| `SYSTEM_CONFIG_CHANGED` | `{key, old_value, new_value}` | Settings |
| `SYSTEM_RESET` | `{}` | Engine |
| `SYSTEM_STANDBY` | `{}` | Engine |
| `SYSTEM_WAKE` | `{}` | Engine |

### UI Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `UI_OPEN_REQUESTED` | `{panel}` | Command, gesture |
| `UI_CLOSE_REQUESTED` | `{}` | Command, hotkey |
| `UI_PANEL_SHOW` | `{panel, name}` | Brain UI |
| `UI_PANEL_HIDE` | `{panel}` | Brain UI |
| `UI_THEME_CHANGED` | `{theme}` | Settings, UI |
| `UI_MODE_CHANGED` | `{mode}` | Interaction engine |

### Input Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `INPUT_KEYBOARD` | `{key, modifiers, action}` | pynput listener |
| `INPUT_MOUSE` | `{x, y, button, action}` | Gesture executor, OS |
| `INPUT_VOICE` | `{text, confidence}` | (Future) Voice plugin |
| `INPUT_GESTURE` | `{gesture, position}` | (Future) Gesture bridge |

### Command Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `COMMAND_EXECUTE` | `{name, params, source}` | `CommandHandler.execute()` |
| `COMMAND_COMPLETE` | `{name, result}` | `CommandHandler` |
| `COMMAND_FAILED` | `{name, error}` | `CommandHandler` |
| `COMMAND_REGISTERED` | `{name, command_cls}` | Registry |
| `COMMAND_UNREGISTERED` | `{name}` | Registry |

### Vision Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `OBJECT_DETECTED` | `{count, objects: [{name, confidence, box, distance_z}]}` | ObjectSpatialPlugin |
| `HAND_DETECTED` | `{hands: [{label, landmarks, gesture, gesture_score}]}` | HandPerceptionPlugin |
| `GESTURE_RECOGNIZED` | `{gesture, action, position, confidence}` | GestureActionExecutor |
| `FACE_DETECTED` | (Future) | (Future) |
| `POSE_DETECTED` | (Future) | (Future) |
| `DEPTH_FRAME` | (Future) | (Future) |
| `HAND_LANDMARKS` | (Future) | (Future) |

### Context Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `CONTEXT_CHANGED` | `{mode, active_app}` | ContextManager |
| `APP_FOCUS_CHANGED` | `{app_name, pid}` | ContextManager |
| `MODE_CHANGED` | `{mode}` | Interaction engine |
| `ENVIRONMENT_CHANGED` | `{env}` | ContextManager |

### Memory Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `MEMORY_OBJECT_ADDED` | `{object_id, name, location}` | ObjectMemory |
| `MEMORY_OBJECT_UPDATED` | `{object_id, changes}` | ObjectMemory |
| `MEMORY_OBJECT_REMOVED` | `{object_id}` | ObjectMemory |
| `MEMORY_SEARCHED` | `{query, results_count}` | ObjectMemory |

### Task Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `TASK_CREATED` | `{task_id, name, type}` | TaskManager |
| `TASK_UPDATED` | `{task_id, status}` | TaskManager |
| `TASK_COMPLETED` | `{task_id}` | TaskManager |
| `TASK_CANCELLED` | `{task_id}` | TaskManager |
| `TASK_DELETED` | `{task_id}` | TaskManager |

### Plugin Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `PLUGIN_LOADED` | `{name}` | PluginManager |
| `PLUGIN_UNLOADED` | `{name}` | PluginManager |
| `PLUGIN_ERROR` | `{name, error}` | PluginManager |
| `PLUGIN_STATE_CHANGED` | `{name, state}` | Plugin |

### Status Events

| EventType | Data Payload | Emitted By |
|-----------|-------------|------------|
| `STATUS_HEALTH` | `{status, details}` | System monitor |
| `STATUS_PERFORMANCE` | `{fps, inference_time}` | PerceptionWorker |
| `STATUS_RESOURCE` | `{cpu, memory, disk}` | ContextManager |
| `STATUS_MODEL` | `{model, loaded}` | Detector/HandTracker |

---

## Thread Safety

- `subscribe()` and `unsubscribe()` are thread-safe (use `threading.Lock`)
- `emit()` dispatches synchronously — handlers run on the emitter's thread
- If a handler raises, other handlers still execute (try/except per handler)
- Handlers that modify shared state must use their own locks

## Best Practices

1. **Subscribe at module init** — set up handlers once, don't subscribe/unsubscribe per frame
2. **Minimize handler work** — handlers should be fast; offload heavy processing to threads
3. **Use `source` field** — always identify your module for debugging
4. **Don't emit during handler** — avoid recursive event chains
5. **Clean up on shutdown** — unsubscribe if your module has a lifecycle
