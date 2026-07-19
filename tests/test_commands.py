import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from commands import CommandRegistry
from commands.remember import RememberCommand
from commands.find import FindCommand
from commands.forget import ForgetCommand
from commands.status import StatusCommand
from memory.object_memory import ObjectMemory
from database.objects import ObjectStore


class TestCommands(unittest.TestCase):
    def setUp(self):
        self.store = ObjectStore(filepath="tests/test_cmd_objects.json")
        self.memory = ObjectMemory(store=self.store)
        self.registry = CommandRegistry()
        self.registry.register(RememberCommand(self.memory))
        self.registry.register(FindCommand(self.memory))
        self.registry.register(ForgetCommand(self.memory))
        self.registry.register(StatusCommand(self.memory))

    def tearDown(self):
        self.store.storage.clear()

    def test_remember_command(self):
        result = self.registry.execute("remember", args=["hammer", "workbench"])
        self.assertTrue(result.success)
        self.assertIn("hammer", result.message.lower())

    def test_find_command(self):
        self.registry.execute("remember", args=["hammer"])
        result = self.registry.execute("find", args=["hammer"])
        self.assertTrue(result.success)
        self.assertEqual(len(result.data), 1)

    def test_forget_command(self):
        self.registry.execute("remember", args=["hammer"])
        obj = self.memory.list_all()[0]
        result = self.registry.execute("forget", args=[obj.id])
        self.assertTrue(result.success)

    def test_status_command(self):
        result = self.registry.execute("status", args=[])
        self.assertTrue(result.success)

    def test_unknown_command(self):
        result = self.registry.execute("unknown")
        self.assertFalse(result.success)

    def test_parse_and_execute(self):
        result = self.registry.parse_and_execute("remember screwdriver toolbox")
        self.assertTrue(result.success)


if __name__ == '__main__':
    unittest.main()
