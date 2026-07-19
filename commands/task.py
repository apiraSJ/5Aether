from commands.base import Command, CommandResult
from memory.models import Task
from tasks.manager import TaskManager
from commands import generate_id


class TaskCommand(Command):
    def __init__(self, task_manager: TaskManager):
        self._task_manager = task_manager

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        return "Create a task. Usage: task <name> [type]"

    def execute(self, **kwargs) -> CommandResult:
        args = kwargs.get("args", [])
        if not args:
            return CommandResult(success=False, message="Usage: task <name> [type]")

        name = " ".join(args)
        task_type = "FIND"
        task_id = generate_id("task")

        task = Task(
            id=task_id,
            name=name,
            type=task_type,
            status="PENDING",
        )
        self._task_manager.create(task)
        return CommandResult(
            success=True,
            message=f"Task created: {task_id} - {name}",
            data={"id": task_id, "name": name}
        )
