import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from memory.models import Task
from tasks.manager import TaskManager
from database.tasks import TaskStore


class TestTaskManager(unittest.TestCase):
    def setUp(self):
        self.store = TaskStore(filepath="tests/test_tasks.json")
        self.manager = TaskManager(store=self.store)

    def tearDown(self):
        self.store.storage.clear()

    def test_create_task(self):
        task = Task(id="t1", name="Find Hammer")
        self.manager.create(task)
        retrieved = self.manager.get("t1")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Find Hammer")
        self.assertEqual(retrieved.status, "PENDING")

    def test_update_status(self):
        task = Task(id="t2", name="Inspect")
        self.manager.create(task)
        self.manager.update_status("t2", "RUNNING")
        self.assertEqual(self.manager.get("t2").status, "RUNNING")

    def test_complete_task(self):
        task = Task(id="t3", name="Task")
        self.manager.create(task)
        self.manager.complete("t3")
        self.assertEqual(self.manager.get("t3").status, "COMPLETED")
        self.assertIsNotNone(self.manager.get("t3").completed_at)

    def test_cancel_task(self):
        task = Task(id="t4", name="Cancel Me")
        self.manager.create(task)
        self.manager.cancel("t4")
        self.assertEqual(self.manager.get("t4").status, "CANCELLED")

    def test_list_by_status(self):
        self.manager.create(Task(id="p1", name="Pending"))
        self.manager.create(Task(id="r1", name="Running"))
        self.manager.update_status("r1", "RUNNING")
        pending = self.manager.list_by_status("PENDING")
        running = self.manager.list_by_status("RUNNING")
        self.assertEqual(len(pending), 1)
        self.assertEqual(len(running), 1)

    def test_remove_task(self):
        task = Task(id="t5", name="Remove Me")
        self.manager.create(task)
        self.manager.remove("t5")
        self.assertIsNone(self.manager.get("t5"))


if __name__ == '__main__':
    unittest.main()
