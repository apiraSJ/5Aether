# Aether Command System Reference

Aether uses an **event-driven command system** (`command/`) where commands are dataclasses executed through the EventBus.

---

## Command Dataclass

```python
from command.command import Command, CommandStatus

cmd = Command(
    name="remember",          # Command name
    params={"name": "hammer", "location": (0.5, 0.3)},  # Arguments
    source="user",            # Who issued it (keyboard, gesture, cli)
    id="cmd_001",             # Auto-generated UUID
    timestamp=...,            # Auto-set
    status=CommandStatus.PENDING,
    result=None,
    error=None,
)
```

### Factory Function

```python
from command.command import create_command

cmd = create_command("open_ui", source="keyboard", panel="system")
```

---

## BaseCommand ABC

```python
from command.command import BaseCommand

class RememberCommand(BaseCommand):
    def execute(self, params: dict, context=None) -> dict:
        # Implement command logic
        return {"success": True, "data": object_id}

    def validate(self, params: dict) -> bool:
        return "name" in params

    def get_help(self) -> str:
        return "remember <name> at <x> <y>"
```

---

## CommandRegistry

```python
from command.command import create_default_registry

registry = create_default_registry()
# Registers: OpenUICommand, CloseUICommand, SwitchPanelCommand,
#            SetModeCommand, GetStatusCommand

# Custom registration
registry.register("my_command", MyCommand())
```

---

## CommandHandler

```python
from command.handler import CommandHandler

handler = CommandHandler(event_bus)
handler.register_commands(registry)

result = handler.execute(cmd)
# Returns CommandResult(success=True, message="...", data={...})
```

### Event Flow

```text
caller → handler.execute(cmd)
           ├─→ emit COMMAND_EXECUTE
           ├─→ run command.execute()
           ├─→ emit COMMAND_COMPLETE or COMMAND_FAILED
           └─→ return CommandResult
```

### CommandResult

```python
@dataclass
class CommandResult:
    success: bool
    message: str
    data: Any = None
```

---

## Built-in Commands

| Command | Parameters | Description |
|---------|-----------|-------------|
| `open_ui` | `panel` (optional) | Open the UI overlay with specified panel |
| `close_ui` | — | Close the UI overlay |
| `switch_panel` | `panel` | Switch to system/developer/settings panel |
| `set_mode` | `mode` | Change mode: normal, developer, presentation |
| `get_status` | — | Return current system status |

---

## Gesture Commands

In the vision pipeline, gestures map to commands via `GestureRouter`:

| Gesture | Action | Cooldown |
|---------|--------|----------|
| `Open_Palm` | Toggle HomeMenu | 1.5s |
| `Closed_Fist` | Close UI / Cancel | 1.5s |
| `Victory` | Show Developer Panel | 1.5s |
| `ILoveYou` | Show Settings Panel | 1.5s |
| `Thumb_Up` | Set Normal Mode | 1.5s |
| `Thumb_Down` | Set Developer Mode | 1.5s |
| `Pointing_Up` | Move Cursor | — |
| `Pinch` (thumb+index) | Click / Select | Edge-triggered |

---

## EventBus Command Events

| EventType | When |
|-----------|------|
| `COMMAND_EXECUTE` | Command execution starts |
| `COMMAND_COMPLETE` | Command succeeds |
| `COMMAND_FAILED` | Command fails |
| `COMMAND_REGISTERED` | New command registered |
| `COMMAND_UNREGISTERED` | Command removed |
| `GESTURE_RECOGNIZED` | Gesture triggers action |
| `INPUT_HOTKEY` | Keyboard hotkey pressed |

---

## Hotkey Mapping

In `brain_main.py`, hotkeys are mapped to commands:

| Hotkey | Command | Parameters |
|--------|---------|-----------|
| `Ctrl+Space` | `open_ui` | `{panel: "system"}` |
| `Escape` | `close_ui` | — |
| `1` | `switch_panel` | `{panel: "system"}` |
| `2` | `switch_panel` | `{panel: "developer"}` |
| `3` | `switch_panel` | `{panel: "settings"}` |
| `Tab` | `set_mode` | `{mode: "developer"}` |
| `M` | `set_mode` | `{mode: "normal"}` |
| `P` | `set_mode` | `{mode: "presentation"}` |
