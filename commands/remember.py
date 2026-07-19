from commands.base import Command, CommandResult
from commands import generate_id
from memory.object_memory import ObjectMemory
from memory.models import SpatialObject


class RememberCommand(Command):
    def __init__(self, memory: ObjectMemory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "remember"

    @property
    def description(self) -> str:
        return "Remember an object. Usage: remember <name> [location]"

    def execute(self, **kwargs) -> CommandResult:
        args = kwargs.get("args", [])
        if not args:
            return CommandResult(success=False, message="Usage: remember <name> [location]")

        name = args[0]
        location = " ".join(args[1:]) if len(args) > 1 else ""
        obj_id = generate_id("obj")

        obj = SpatialObject(
            id=obj_id,
            name=name,
            location=location,
        )
        self._memory.add(obj)
        return CommandResult(
            success=True,
            message=f"Object stored: {obj_id} ({name})",
            data={"id": obj_id, "name": name}
        )
