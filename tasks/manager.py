import logging
import time
from typing import List, Optional
from datetime import datetime
from memory.models import Task
from database.tasks import TaskStore


class TaskManager:
    def __init__(self, store: TaskStore = None):
        self.logger = logging.getLogger("Aether.TaskManager")
        self.store = store or TaskStore()
        self._tasks = {}
        self._load_all()

    def _load_all(self):
        raw = self.store.list_all()
        self._tasks = {}
        for task_id, task_data in raw.items():
            try:
                self._tasks[task_id] = Task.from_dict(task_data)
            except Exception as e:
                self.logger.warning(f"Failed to load task {task_id}: {e}")

    def create(self, task: Task) -> str:
        self._tasks[task.id] = task
        self.store.save(task.id, task.to_dict())
        self.logger.info(f"Task created: {task.id} - {task.name}")
        return task.id

    def update_status(self, task_id: str, status: str) -> bool:
        if task_id not in self._tasks:
            return False
        task = self._tasks[task_id]
        task.status = status
        now = datetime.now().isoformat()
        if status == "RUNNING" and not task.started_at:
            task.started_at = now
        elif status in ("COMPLETED", "CANCELLED"):
            task.completed_at = now
        self.store.save(task_id, task.to_dict())
        self.logger.info(f"Task {task_id} status: {status}")
        return True

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def list_all(self) -> List[Task]:
        return list(self._tasks.values())

    def list_by_status(self, status: str) -> List[Task]:
        return [t for t in self._tasks.values() if t.status == status]

    def cancel(self, task_id: str) -> bool:
        return self.update_status(task_id, "CANCELLED")

    def complete(self, task_id: str) -> bool:
        return self.update_status(task_id, "COMPLETED")

    def remove(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self.store.delete(task_id)
            return True
        return False

    @property
    def count(self) -> int:
        return len(self._tasks)

    @property
    def active_count(self) -> int:
        return len([t for t in self._tasks.values() if t.status in ("PENDING", "RUNNING")])
