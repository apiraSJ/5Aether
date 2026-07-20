from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Callable
import logging

from command.command import Command, CommandStatus, BaseCommand
from core.event_bus import EventBus, EventType, Event


@dataclass
class CommandResult:
    success: bool
    data: Any = None
    error: str = ""


class CommandHandler:
    """Handles command execution and result reporting."""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.commands: Dict[str, BaseCommand] = {}
        self.logger = logging.getLogger("Aether.CommandHandler")
    
    def register(self, command: BaseCommand) -> None:
        self.commands[command.name] = command
        self.logger.debug(f"Registered command: {command.name}")
    
    def unregister(self, name: str) -> None:
        self.commands.pop(name, None)
    
    def execute(self, command: Command) -> CommandResult:
        """Execute a command."""
        self.logger.info(f"Executing: {command.name} (source: {command.source})")
        
        command.status = CommandStatus.EXECUTING
        self._emit_status(command)
        
        try:
            # Find command handler
            handler = self.commands.get(command.name)
            if not handler:
                raise ValueError(f"Unknown command: {command.name}")
            
            # Execute
            result = handler.execute(command.params, context=None)
            
            command.status = CommandStatus.COMPLETED
            command.result = result
            
            self._emit_status(command)
            self._emit_complete(command, result)
            
            return CommandResult(success=True, data=result)
            
        except Exception as e:
            self.logger.error(f"Command {command.name} failed: {e}")
            command.status = CommandStatus.FAILED
            command.error = str(e)
            
            self._emit_status(command)
            self._emit_failed(command, str(e))
            
            return CommandResult(success=False, error=str(e))
    
    def _emit_status(self, command: Command):
        self.event_bus.emit_simple(EventType.COMMAND_EXECUTE, {
            "command": command.to_dict()
        }, source="command_handler")
    
    def _emit_complete(self, command: Command, result: Any):
        self.event_bus.emit_simple(EventType.COMMAND_COMPLETE, {
            "command_id": command.command_id,
            "name": command.name,
            "result": str(result) if result else None
        }, source="command_handler")
    
    def _emit_failed(self, command: Command, error: str):
        self.event_bus.emit_simple(EventType.COMMAND_FAILED, {
            "command_id": command.command_id,
            "name": command.name,
            "error": error
        }, source="command_handler")