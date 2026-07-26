# Aether — How to Run

## Current Entry Points

| File                      | Purpose                                                               | Status                  |
| ------------------------- | --------------------------------------------------------------------- | ----------------------- |
| `python run.py`           | Primary v2 entry — boots `AetherApp`, dispatches demo commands, idles | ✅ Works                 |
| `python aether/app_v2.py` | Minimal `AetherApplication.run()` for Phase B tick loop               | ✅ Works                 |
| `python -m aether.app`    | Same as `run.py` via module                                           | ✅ Works                 |
| `python main.py`          | Legacy v1 — full camera + gesture + DearPyGui pipeline                | ⚠️ Works but deprecated |

## Quick Start

### Recommended: v2 boot proof

```bash
python run.py
```

### With explicit config

```bash
python run.py --config config/default.yaml
```

### Phase B app (tick loop)

```bash
python aether/app_v2.py
```

## Config

* **v2:** `config/default.yaml` — plugins, logging, app name/version
* **v1:** `config/desktop.yaml` — legacy settings

---

## Workflow Cycle (v2 Architecture)

```text
AetherApplication.tick()  (30 Hz by default)
├─ CommandBus.update()
│  ├─ Dequeue commands FIFO
│  ├─ Execute handlers
│  └─ Emit lifecycle events
├─ Services.update(dt)
│  └─ Domain logic
├─ Plugins.update(dt)
│  ├─ KeyboardPlugin → reads keys → CommandBus.dispatch()
│  ├─ HandPlugin → reads camera → CommandBus.dispatch()
│  └─ GUIPlugin → renders PySide6
├─ EventBus.flush()
│  └─ Deliver all queued events FIFO
└─ Rate limit
   └─ Sleep to target 30 Hz
```

## Data Flow: Input → Command → Result

```text
[Keyboard]        [Camera]         [Voice]         [XR Controller]
     │               │                │                   │
     ▼               ▼                ▼                   ▼
Tickable Plugins (Input Adapters)
KeyboardInputPlugin | HandPerceptionPlugin | VoicePlugin
     │               │                │                   │
     └───────────────┴───────────────┴───────────────────┘
                             │
                             ▼
                 CommandBus.dispatch(Command)
                 (name, source, params, context, target)
                             │
                             ▼
                 CommandBus.update() — executes queue
                 ├─ handler(command) → returns Any
                 ├─ Command.status = COMPLETED / FAILED
                 └─ Emits command.issued / command.started /
                    command.completed / command.failed
                             │
                             ▼
               ResultPipeline.publish(CommandResult)
               ├─ success → [notification, history, layout]
               └─ error   → [notification, history]
```

---

## What to Delete (Legacy v1)

These root-level directories are fully superseded by `aether/`:

```text
core/           → aether/core/ + plugins/
perception/     → aether/phase_d/hand_plugin.py + future vision plugins
vision/         → aether/plugins/ (to be created)
interface/      → aether/plugins/gui_plugin.py + future workspace UI
command/        → aether/core/command_bus.py + handler plugins
memory/         → aether/memory/ + SQLite service
database/       → aether/memory/ (SQLite stores)
tasks/          → aether/domain/task/ (to be created)
context/        → aether/domain/context/ (to be created)
interaction/    → aether/plugins/ (pointer events + focus manager)
```

Also deletable:

* `brain_main.py` — old brain-only entry
* `brain_server.py` — unused
* `config.py` — replaced by `aether.config.loader`
* `help.txt` — redundant
* `inspect_dpg.py` — debug script
* `spatial_core.py` — unused
* `test_main.py`, `test_brain.py` — replaced by `tests/phase_a/`
* `TUTORIALS.md` — replaced by `docs/GETTING_STARTED.md`
* `ui/` — empty
* `plugins/` — empty

---

## Next Steps (Phase 1)

1. **Single entry**: `python -m aether --mode vision|brain|headless|cli`
2. **Command parity**: Implement all v1 commands as handlers registered via plugins
3. **Perception plugin**: Port `HandPerceptionPlugin` to `TickablePlugin` → emit `PointerEvent` → `GestureToIntentResolver` → `CommandBus`
4. **ResultPipeline handlers**: `NotificationHandler`, `HistoryHandler`, `LayoutHandler`