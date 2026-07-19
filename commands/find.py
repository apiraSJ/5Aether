from commands.base import Command, CommandResult
from memory.object_memory import ObjectMemory


class FindCommand(Command):
    def __init__(self, memory: ObjectMemory):
        self._memory = memory

    @property
    def name(self) -> str:
        return "find"

    @property
    def description(self) -> str:
        return "Find objects by name. Usage: find <query>"

    def execute(self, **kwargs) -> CommandResult:
        args = kwargs.get("args", [])
        if not args:
            return CommandResult(success=False, message="Usage: find <query>")

        query = " ".join(args)
        results = self._memory.search_by_name(query)

        if not results:
            return CommandResult(success=False, message=f"No objects found matching '{query}'")

        items = []
        for obj in results:
            items.append({
                "id": obj.id,
                "name": obj.name,
                "location": obj.location,
                "status": obj.status,
                "last_seen": obj.last_seen,
            })
        return CommandResult(
            success=True,
            message=f"Found {len(results)} object(s)",
            data=items
        )
