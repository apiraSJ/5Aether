import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from memory.models import SpatialObject, Task
from memory.object_memory import ObjectMemory
from database.objects import ObjectStore


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.store = ObjectStore(filepath="tests/test_objects.json")
        self.memory = ObjectMemory(store=self.store)

    def tearDown(self):
        self.store.storage.clear()

    def test_add_and_get(self):
        obj = SpatialObject(id="test_01", name="Hammer", location="Workbench")
        self.memory.add(obj)
        retrieved = self.memory.get("test_01")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Hammer")

    def test_update(self):
        obj = SpatialObject(id="test_02", name="Wrench")
        self.memory.add(obj)
        self.memory.update("test_02", location="Toolbox")
        updated = self.memory.get("test_02")
        self.assertEqual(updated.location, "Toolbox")

    def test_remove(self):
        obj = SpatialObject(id="test_03", name="Screwdriver")
        self.memory.add(obj)
        self.memory.remove("test_03")
        self.assertIsNone(self.memory.get("test_03"))

    def test_search_by_name(self):
        self.memory.add(SpatialObject(id="h1", name="Hammer"))
        self.memory.add(SpatialObject(id="w1", name="Wrench"))
        results = self.memory.search_by_name("hammer")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, "h1")

    def test_list_all(self):
        self.memory.add(SpatialObject(id="a1", name="A"))
        self.memory.add(SpatialObject(id="b1", name="B"))
        self.assertEqual(self.memory.count, 2)

    def test_get_by_location(self):
        self.memory.add(SpatialObject(id="l1", name="A", location="Workbench"))
        self.memory.add(SpatialObject(id="l2", name="B", location="Toolbox"))
        results = self.memory.get_by_location("Workbench")
        self.assertEqual(len(results), 1)


if __name__ == '__main__':
    unittest.main()
