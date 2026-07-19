from commands.base import Command, CommandResult
from memory.object_memory import ObjectMemory
from tasks.manager import TaskManager


class ListCommand(Command):
    def __init__(self, memory: ObjectMemory = None, task_manager: TaskManager = None):
        self._memory = memory
        self._task_manager = task_manager

    @property
    def name(self) -> str:
        return "list"

    @property
    def description(self) -> str:
        return "List objects or tasks. Usage: list [objects|tasks]"

    def execute(self, **kwargs) -> CommandResult:
        args = kwargs.get("args", [])
        target = args[0] if args else "objects"

        if target == "objects" and self._memory:
            objects = self._memory.list_all()
            items = [{"id": o.id, "name": o.name, "location": o.location, "status": o.status} for o in objects]
            return CommandResult(success=True, message=f"{len(items)} object(s)", data=items)

        elif target == "tasks" and self._task_manager:
            tasks = self._task_manager.list_all()
            items = [{"id": t.id, "name": t.name, "status": t.status} for t in tasks]
            return CommandResult(success=True, message=f"{len(items)} task(s)", data=items)

        return CommandResult(success=False, message=f"Unknown list target: {target}")
