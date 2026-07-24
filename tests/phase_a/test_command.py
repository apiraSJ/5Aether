"""Tests for Command and CommandResult dataclasses."""
from aether.core.command import Command
from aether.core.command_result import CommandResult


class TestCommand:
    def test_create(self):
        c = Command(name="test.cmd", source="test")
        assert c.name == "test.cmd"
        assert c.source == "test"
        assert c.id  # auto-generated
        assert c.created_at > 0

    def test_empty_name_raises(self):
        try:
            Command(name="", source="test")
            assert False, "Should have raised"
        except ValueError:
            pass

    def test_empty_source_raises(self):
        try:
            Command(name="test.cmd", source="")
            assert False, "Should have raised"
        except ValueError:
            pass

    def test_params(self):
        c = Command(name="x", source="y", params={"a": 1})
        assert c.params == {"a": 1}


class TestCommandResult:
    def test_ok(self):
        r = CommandResult.ok("id1", "cmd1", message="done")
        assert r.success
        assert r.message == "done"
        assert r.notification is None

    def test_fail(self):
        r = CommandResult.fail("id1", "cmd1", error="boom")
        assert not r.success
        assert r.error == "boom"
        assert r.notification is None  # Fixed: no longer defaults to "toast"

    def test_fail_with_notification(self):
        r = CommandResult.fail("id1", "cmd1", error="x", notification="toast")
        assert r.notification == "toast"
