from commands.base import Command, CommandResult
from memory.object_memory import ObjectMemory


class ForgetCommand(Command):
    def __init__(self, memory: ObjectMemory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "forget"

    @property
    def description(self) -> str:
        return "Remove an object from memory. Usage: forget <object_id>"

    def execute(self, **kwargs) -> CommandResult:
        args = kwargs.get("args", [])
        if not args:
            return CommandResult(success=False, message="Usage: forget <object_id>")

        object_id = args[0]
        removed = self._memory.remove(object_id)

        if removed:
            return CommandResult(success=True, message=f"Object forgotten: {object_id}")
        return CommandResult(success=False, message=f"Object not found: {object_id}")
