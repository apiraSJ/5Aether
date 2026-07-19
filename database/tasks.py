import os
import logging
from database.storage import JsonStorage


class TaskStore:
    def __init__(self, filepath: str = "database/tasks.json"):
        self.logger = logging.getLogger("Aether.TaskStore")
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self.storage = JsonStorage(filepath)

    def save(self, task_id: str, task_data: dict):
        self.storage.set(task_id, task_data)

    def load(self, task_id: str) -> dict:
        return self.storage.get(task_id)

    def delete(self, task_id: str) -> bool:
        return self.storage.delete(task_id)

    def list_all(self) -> dict:
        return self.storage.all()

    def list_by_status(self, status: str) -> list:
        return [t for t in self.storage.values() if t.get("status") == status]
