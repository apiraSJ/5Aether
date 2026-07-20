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
python -m pytest tests/ -v   # Verify 84 tests pass
```

---

## Project Structure

```text
core/          App lifecycle, EventBus, FrameBroker, Settings
perception/    Daemon threads: HandPerceptionPlugin, ObjectSpatialPlugin
vision/        Computer vision: hand tracker, gesture engine, spatial/PnP
ui/            DearPyGui dashboard
interface/     PySide6 floating overlay
command/       Event-driven command system (brain path)
commands/      Direct-execution command implementations
memory/        ObjectMemory cache + data models
database/      JSON file storage
plugins/       Plugin ABC implementations
tasks/         TaskManager
context/       Active window detection
models/        MediaPipe + YOLO weights
tests/         pytest test suite (84 tests, 9 files)
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
2. **Thread Safety**: All shared state must use `threading.Lock`. The global `state_lock` pattern in `main.py` is the reference.
3. **Brain-First Philosophy**: Sensors are plugins. The intelligence layer is the core.
4. **Graceful Degradation**: DearPyGui → OpenCV fallback; GestureRecognizer → finger-counting fallback.

### Testing

```bash
pytest -v                    # All tests
pytest tests/test_gesture_actions.py -v   # Gesture system
pytest tests/test_event_bus.py -v         # EventBus
```

- All new features should include tests
- Run the full suite before submitting
- 84 tests should always pass

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
from core.frame_broker import FrameBroker
from core.event_bus import EventBus, EventType

class MyPlugin(threading.Thread):
    def __init__(self, broker, bus, config=None):
        super().__init__(daemon=True)
        self.broker = broker
        self.bus = bus
        self._running = True

    def run(self):
        while self._running:
            self.broker.new_frame_event.wait(timeout=1.0)
            frame = self.broker.get_frame()
            self.broker.clear_event()
            if frame is None:
                continue
            result = self.process(frame)
            self.bus.emit(EventType.CUSTOM_EVENT, data=result, source="my_plugin")

    def stop(self):
        self._running = False
        self.broker.new_frame_event.set()
        self.join(timeout=2.0)
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
| `TUTORIALS.md` | Installation and usage |
| `docs/ARCHITECTURE.md` | Complete system design |
| `docs/ROADMAP.md` | Future development plan |
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
- Run `python brain_main.py` and press `H` for in-app help
