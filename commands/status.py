from commands.base import Command, CommandResult
from memory.object_memory import ObjectMemory


class StatusCommand(Command):
    def __init__(self, memory: ObjectMemory = None):
        self._memory = memory

    @property
    def name(self) -> str:
        return "status"

    @property
    def description(self) -> str:
        return "Show system status or object details. Usage: status [object_id]"

    def execute(self, **kwargs) -> CommandResult:
        args = kwargs.get("args", [])

        if args and self._memory:
            object_id = args[0]
            obj = self._memory.get(object_id)
            if obj:
                return CommandResult(
                    success=True,
                    message=f"Object: {obj.name}",
                    data={
                        "id": obj.id,
                        "name": obj.name,
                        "location": obj.location,
                        "status": obj.status,
                        "position_3d": list(obj.position_3d),
                        "last_seen": obj.last_seen,
                    }
                )
            return CommandResult(success=False, message=f"Object not found: {object_id}")

        if self._memory:
            return CommandResult(
                success=True,
                message=f"Memory: {self._memory.count} object(s)",
                data={"object_count": self._memory.count}
            )

        return CommandResult(success=True, message="System operational")
