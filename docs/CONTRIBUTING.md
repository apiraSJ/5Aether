# Contributing to Aether

Thank you for your interest in Aether! This document provides guidelines for contributing.

---

## Getting Started

```bash
git clone <repo-url> Aether
cd Aether
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/ -v   # Verify all tests pass
```

---

## Project Structure

```text
core/          App lifecycle, EventBus, FrameBroker, Settings, Plugin/Module systems
perception/    Daemon threads: HandPerceptionPlugin, ObjectSpatialPlugin
vision/        Computer vision: hand tracker, gesture engine, spatial/PnP, calibration
interface/     PySide6 floating overlay: AetherUI, HomeMenu, CursorOverlay, StatusBar
command/       Event-driven command system with CommandHandler
memory/        ObjectMemory cache + data models (SpatialObject, Task, EventRecord)
database/      JSON file storage: JsonStorage, ObjectStore, TaskStore, EventStore
tasks/         TaskManager with status lifecycle
context/       Active window detection, CPU/memory monitoring
interaction/   State machine, focus manager, interaction coordinator
models/        MediaPipe + YOLO weights
tests/         pytest test suite (8 files)
docs/          Documentation (8 files)
```

---

## Development Guidelines

### Code Style

- **No comments** unless absolutely necessary — code should be self-documenting
- Use descriptive names: `on_hand_update`, not `handler1`
- Typed Python where reasonable (use type hints for public APIs)
- Follow existing patterns in the file you're editing

### Architecture Rules

1. **Event-Driven Communication**: No module calls another directly. Use EventBus.
2. **Thread Safety**: All shared state must use `threading.Lock`.
3. **Brain-First Philosophy**: Sensors are plugins. The intelligence layer is the core.
4. **Graceful Degradation**: DearPyGui → OpenCV fallback; GestureRecognizer → finger-counting fallback.
5. **Main Thread Safety**: Qt widgets must only be updated from the main thread. Use `ActionQueue` to bridge from perception threads.

### Testing

```bash
pytest -v                    # All tests
pytest tests/test_gesture_actions.py -v   # Gesture system
pytest tests/test_event_bus.py -v         # EventBus
```

- All new features should include tests
- Run the full suite before submitting

### Commits

We don't enforce a specific format, but prefer descriptive commit messages that explain *what* and *why*.

---

## Adding a New Feature

1. **Explore the codebase** — find the closest existing pattern
2. **Wire through EventBus** — define new `EventType` if needed
3. **Update configuration** — add keys to `config/desktop.yaml` and `core/settings.py`
4. **Write tests** — add to existing test file or create new one in `tests/`
5. **Update docs** — if adding a public API, update `docs/API.md`

### Example: New Perception Plugin

```python
# perception/my_plugin.py
import threading
from core.frame_broker import FrameBroker
from core.event_bus import EventBus, EventType

class MyPlugin(threading.Thread):
    def __init__(self, broker, bus, config=None):
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
            result = self.process(frame)
            self.bus.emit(EventType.CUSTOM_EVENT, data=result, source="my_plugin")

    def process(self, frame):
        # Your processing logic
        return {}

    def stop(self):
        self._running = False
        self._frame_event.set()
        self.join(timeout=2.0)
        self.broker.unregister_consumer("my_plugin")
```

---

## Known Issues to Tackle

- **tracking.py** — placeholder, needs real tracking (ByteTrack/BoT-SORT)
- **Fusion Engine** — hand+object spatial fusion not implemented
- **Face/Pose models** — MediaPipe models available but not integrated
- **Depth estimation** — no stereo or depth camera support
- **AI reasoning** — no LLM integration yet

See `docs/ROADMAP.md` for the full development plan.

---

## Documentation

| File | Contents |
|------|----------|
| `README.md` | Project overview (1-2 minute read) |
| `docs/ARCHITECTURE.md` | Complete system architecture |
| `docs/ROADMAP.md` | Development roadmap |
| `docs/PLUGINS.md` | Plugin development guide |
| `docs/COMMANDS.md` | Command framework |
| `docs/MEMORY.md` | Memory system |
| `docs/EVENTS.md` | EventBus event types |
| `docs/API.md` | Public API reference |

---

## Getting Help

- Open an issue on GitHub
- Check `docs/ARCHITECTURE.md` for system design
- Check `docs/API.md` for API usage
