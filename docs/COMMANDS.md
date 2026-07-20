# Aether Command System Reference

Aether has two command frameworks: an **event-driven system** used by the brain path and a **direct-execution system** used by the CLI.

---

## 1. Event-Driven Command System (`command/`)

Used by `brain_main.py`. Commands are dataclasses passed through the EventBus.

### Command Dataclass

```python
from command.command import Command, CommandStatus

cmd = Command(
    name="remember",          # Command name
    params={"name": "hammer", "location": (0.5, 0.3)},  # Arguments
    source="user",            # Who issued it
    id="cmd_001",             # Auto-generated
    timestamp=...,            # Auto-set
    status=CommandStatus.PENDING,
    result=None,
    error=None,
)
```

### BaseCommand ABC

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

### CommandRegistry

```python
from command.command import create_default_registry

registry = create_default_registry()
# Registers: OpenUICommand, CloseUICommand, SwitchPanelCommand, 
#            SetModeCommand, GetStatusCommand

# Custom registration
registry.register("my_command", MyCommand())
```

### CommandHandler

```python
from command.handler import CommandHandler

handler = CommandHandler(event_bus)
handler.register_commands(registry)

result = handler.execute(cmd)
# Returns CommandResult(success=True, message="...", data={...})
# Also emits COMMAND_EXECUTE and COMMAND_COMPLETE/FAILED on EventBus
```

### Event Flow

```text
caller → handler.execute(cmd)
           ├─→ emit COMMAND_EXECUTE
           ├─→ run command.execute()
           ├─→ emit COMMAND_COMPLETE or COMMAND_FAILED
           └─→ return CommandResult
```

---

## 2. Direct-Execution Command System (`commands/`)

Used by the CLI and interactive shell.

### Command ABC

```python
from commands.base import Command, CommandResult

class FindCommand(Command):
    def execute(self, **kwargs) -> CommandResult:
        name = kwargs.get("name", "")
        results = memory.search_by_name(name)
        return CommandResult(
            success=True,
            message=f"Found {len(results)} object(s)",
            data=results,
        )
```

### CommandRegistry

```python
from commands import CommandRegistry

registry = CommandRegistry()
registry.register(RememberCommand())
registry.register(FindCommand())
registry.register(ForgetCommand())
registry.register(ListCommand())
registry.register(StatusCommand())
registry.register(TaskCommand())

# Parse and execute from text
result = registry.parse_and_execute("remember hammer at 0.5 0.3")
```

### Built-in Commands

| Command | Syntax | Description |
|---------|--------|-------------|
| `RememberCommand` | `remember <name> at <x> <y>` | Store object in memory |
| `FindCommand` | `find <name>` | Search by name (case-insensitive) |
| `ForgetCommand` | `forget <id>` | Remove by object ID |
| `ListCommand` | `list` | List all objects |
| `StatusCommand` | `status [id]` | Show count or object details |
| `TaskCommand` | `task create <name> <type>` | Create a task |

### Output

All commands return `CommandResult`:

```python
@dataclass
class CommandResult:
    success: bool
    message: str
    data: Any = None
```

Example:
```python
CommandResult(success=True, message="Remembered 'hammer' as tool", data={"id": "obj_001"})
```

---

## 3. Gesture Commands (main.py)

In the vision pipeline, gestures map to commands via `GESTURE_COMMAND_MAP`:

```python
GESTURE_COMMAND_MAP = {
    "Closed_Fist":  "Cancel / Close",
    "Open_Palm":    "Toggle UI",
    "Pointing_Up":  "Move Cursor",
    "Thumb_Up":     "Confirm / Accept",
    "Thumb_Down":   "Reject / Deny",
    "Victory":      "Copy / Select",
    "ILoveYou":     "Show Help",
    "Unknown":      "",
}
```

These are displayed in tkinter popups and on the DPG sidebar.

---

## 4. EventBus Commands

The EventBus carries command-related events:

| EventType | Emitted When |
|-----------|-------------|
| `COMMAND_EXECUTE` | Command execution starts |
| `COMMAND_COMPLETE` | Command succeeds |
| `COMMAND_FAILED` | Command fails |
| `COMMAND_REGISTERED` | New command registered |
| `COMMAND_UNREGISTERED` | Command removed |
| `GESTURE_RECOGNIZED` | Gesture triggers action |

See `docs/EVENTS.md` for details.
