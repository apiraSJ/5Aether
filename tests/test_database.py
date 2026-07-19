import unittest
import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.storage import JsonStorage


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.storage = JsonStorage(filepath="tests/test_db.json")

    def tearDown(self):
        if os.path.exists("tests/test_db.json"):
            os.remove("tests/test_db.json")

    def test_set_and_get(self):
        self.storage.set("key1", {"name": "test"})
        result = self.storage.get("key1")
        self.assertEqual(result["name"], "test")

    def test_delete(self):
        self.storage.set("key2", "value")
        self.storage.delete("key2")
        self.assertIsNone(self.storage.get("key2"))

    def test_keys(self):
        self.storage.set("a", 1)
        self.storage.set("b", 2)
        self.assertEqual(len(self.storage.keys()), 2)

    def test_persistence(self):
        self.storage.set("persist", "data")
        storage2 = JsonStorage(filepath="tests/test_db.json")
        self.assertEqual(storage2.get("persist"), "data")

    def test_clear(self):
        self.storage.set("x", 1)
        self.storage.clear()
        self.assertEqual(len(self.storage), 0)


if __name__ == '__main__':
    unittest.main()
