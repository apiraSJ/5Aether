import uuid
import logging
from typing import Dict, Type, Optional
from commands.base import Command, CommandResult


class CommandRegistry:
    def __init__(self):
        self.logger = logging.getLogger("Aether.CommandRegistry")
        self._commands: Dict[str, Command] = {}

    def register(self, command: Command):
        self._commands[command.name] = command
        self.logger.info(f"Command registered: {command.name}")

    def unregister(self, name: str):
        self._commands.pop(name, None)

    def execute(self, command_name: str, **kwargs) -> CommandResult:
        command = self._commands.get(command_name)
        if not command:
            return CommandResult(
                success=False,
                message=f"Unknown command: {command_name}"
            )
        try:
            result = command.execute(**kwargs)
            self.logger.info(f"Command executed: {command_name} -> {result.success}")
            return result
        except Exception as e:
            self.logger.error(f"Command failed: {command_name}: {e}")
            return CommandResult(success=False, message=str(e))

    def parse_and_execute(self, text: str) -> CommandResult:
        parts = text.strip().split()
        if not parts:
            return CommandResult(success=False, message="Empty command")

        command_name = parts[0].lower()
        args = parts[1:]

        return self.execute(command_name, args=args, raw_text=text)

    def list_commands(self) -> Dict[str, str]:
        return {name: cmd.description for name, cmd in self._commands.items()}

    def get_command(self, name: str) -> Optional[Command]:
        return self._commands.get(name)


def generate_id(prefix: str = "obj") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"
