from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from enum import Enum
import uuid
import time


class CommandStatus(Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Command:
    """Base command class - represents an action to execute."""
    name: str
    params: Dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"  # keyboard, gesture, voice, auto
    command_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    status: CommandStatus = CommandStatus.PENDING
    result: Any = None
    error: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "name": self.name,
            "params": self.params,
            "source": self.source,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "result": str(self.result) if self.result else None,
            "error": self.error
        }


def create_command(name: str, source: str = "keyboard", **params) -> Command:
    """Factory function to create commands easily."""
    return Command(name=name, source=source, params=params)


class BaseCommand(ABC):
    """Abstract base for executable commands."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
    
    @abstractmethod
    def execute(self, params: Dict[str, Any], context: Any = None) -> Any:
        """Execute the command with given parameters."""
        pass
    
    def validate(self, params: Dict[str, Any]) -> bool:
        """Validate command parameters."""
        return True
    
    def get_help(self) -> str:
        return f"{self.name}: {self.description}"


class CommandRegistry:
    """Registry of all available commands."""
    
    def __init__(self):
        self._commands: Dict[str, BaseCommand] = {}
    
    def register(self, command: BaseCommand) -> None:
        self._commands[command.name] = command
    
    def unregister(self, name: str) -> None:
        self._commands.pop(name, None)
    
    def get(self, name: str) -> Optional[BaseCommand]:
        return self._commands.get(name)
    
    def list_commands(self) -> Dict[str, str]:
        return {name: cmd.description for name, cmd in self._commands.items()}
    
    def execute(self, name: str, params: Dict[str, Any], context: Any = None) -> Any:
        """Execute a command by name."""
        cmd = self.get(name)
        if not cmd:
            raise ValueError(f"Unknown command: {name}")
        if not cmd.validate(params):
            raise ValueError(f"Invalid parameters for {name}")
        return cmd.execute(params, context)


# Core system commands
class OpenUICommand(BaseCommand):
    def __init__(self):
        super().__init__("open_ui", "Open the Aether UI")
    
    def execute(self, params: Dict[str, Any], context: Any = None) -> Any:
        panel = params.get("panel", "system")
        if context and hasattr(context, 'ui'):
            context.ui.show()
            context.ui.show_panel(panel)
        return {"panel": panel}


class CloseUICommand(BaseCommand):
    def __init__(self):
        super().__init__("close_ui", "Close the Aether UI")
    
    def execute(self, params: Dict[str, Any], context: Any = None) -> Any:
        if context and hasattr(context, 'ui'):
            context.ui.hide()
        return {"closed": True}


class SwitchPanelCommand(BaseCommand):
    def __init__(self):
        super().__init__("switch_panel", "Switch UI panel")
    
    def execute(self, params: Dict[str, Any], context: Any = None) -> Any:
        panel = params.get("panel", "system")
        if context and hasattr(context, 'ui'):
            context.ui.show_panel(panel)
        return {"panel": panel}


class SetModeCommand(BaseCommand):
    def __init__(self):
        super().__init__("set_mode", "Set UI mode (normal/developer/presentation)")
    
    def execute(self, params: Dict[str, Any], context: Any = None) -> Any:
        mode = params.get("mode", "normal")
        if context and hasattr(context, 'ui'):
            context.ui.set_mode(mode)
        return {"mode": mode}


class GetStatusCommand(BaseCommand):
    def __init__(self):
        super().__init__("get_status", "Get system status")
    
    def execute(self, params: Dict[str, Any], context: Any = None) -> Any:
        status = {}
        if context:
            if hasattr(context, 'engine'):
                status["engine"] = context.engine.get_status()
            if hasattr(context, 'context_manager'):
                ctx = context.context_manager.get_context()
                status["context"] = {
                    "mode": ctx.mode,
                    "app": ctx.current_app,
                    "cpu": ctx.cpu_percent,
                    "memory": ctx.memory_percent
                }
        return status


def create_default_registry() -> CommandRegistry:
    """Create a registry with all default commands."""
    registry = CommandRegistry()
    registry.register(OpenUICommand())
    registry.register(CloseUICommand())
    registry.register(SwitchPanelCommand())
    registry.register(SetModeCommand())
    registry.register(GetStatusCommand())
    return registry