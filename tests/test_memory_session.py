"""Tests for M1 Memory UX — work sessions, boot restore, memory.continue.

WorkSession lives in the "working" table under WORK_SESSION_KEY. These tests
cover the MemoryManager session API, the MemoryPlugin boot-restore event, and
the memory.continue command (reconstruct / start / append).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import EventBus
from aether.core.service_container import ServiceContainer
from aether.memory.memory_manager import MemoryManager, WORK_SESSION_KEY
from aether.plugins.memory_plugin import MemoryPlugin

from tests.test_memory_plugin import SEED_COUNT


@pytest.fixture
def container():
    c = ServiceContainer()
    c.register_instance("event_bus", EventBus(queued=False))
    c.register_instance("command_bus", CommandBus())
    return c


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "memory.db")


@pytest.fixture
def plugin(container, db_path):
    p = MemoryPlugin()
    p._db_path = db_path
    p.initialize(container)
    p.start()
    yield p
    try:
        p.stop()
    except Exception:
        pass


class TestWorkSessionCRUD:
    def test_create_session_stores_working_record(self, plugin):
        plugin._memory.create_session("C3 cleanup in the Aether repo", ["fix layout paths"])
        result = plugin._memory.recall(WORK_SESSION_KEY, "working")
        assert result.found
        record = result.records[0]
        assert record.value["summary"] == "C3 cleanup in the Aether repo"
        assert record.value["key_facts"] == ["fix layout paths"]

    def test_create_session_returns_id_and_emits_event(self, plugin, container):
        captured = []
        container.resolve("event_bus").subscribe("memory.session.created", lambda e: captured.append(e))
        record_id = plugin._memory.create_session("Build the M1 memory UX")
        assert record_id
        assert captured and captured[0].payload["summary"] == "Build the M1 memory UX"

    def test_create_session_replaces_previous(self, plugin):
        plugin._memory.create_session("first task", ["fact a"])
        plugin._memory.create_session("second task", ["fact b"])
        session = plugin._memory.get_latest_session()
        assert session["summary"] == "second task"
        assert session["key_facts"] == ["fact b"]
        # Only one current-session record is kept.
        result = plugin._memory.recall(WORK_SESSION_KEY, "working")
        assert result.total == 1

    def test_create_session_requires_summary(self, plugin):
        with pytest.raises(ValueError):
            plugin._memory.create_session("")

    def test_get_latest_session_none_when_empty(self, plugin):
        assert plugin._memory.get_latest_session() is None

    def test_get_latest_session_returns_safe_dict(self, plugin):
        plugin._memory.create_session("Fix layout manager paths", ["path A", "path B"])
        session = plugin._memory.get_latest_session()
        assert set(session) == {"id", "summary", "key_facts", "updated_at"}
        assert session["summary"] == "Fix layout manager paths"
        assert session["key_facts"] == ["path A", "path B"]

    def test_append_session_fact_adds_to_current(self, plugin):
        plugin._memory.create_session("Refactor the repository")
        assert plugin._memory.append_session_fact("Migrate to WAL mode")
        session = plugin._memory.get_latest_session()
        assert session["key_facts"] == ["Migrate to WAL mode"]

    def test_append_session_fact_no_duplicates(self, plugin):
        plugin._memory.create_session("Refactor the repository")
        plugin._memory.append_session_fact("Combine the modules")
        plugin._memory.append_session_fact("Combine the modules")
        session = plugin._memory.get_latest_session()
        assert session["key_facts"] == ["Combine the modules"]

    def test_append_session_fact_when_no_session_returns_false(self, plugin):
        assert plugin._memory.append_session_fact("no session yet") is False

    def test_append_session_fact_empty_string_returns_false(self, plugin):
        plugin._memory.create_session("Fixed task")
        assert plugin._memory.append_session_fact("   ") is False


class TestBootSessionRestore:
    def test_start_publishes_session_restored_when_session_exists(self, container, db_path):
        p1 = MemoryPlugin()
        p1._db_path = db_path
        p1.initialize(container)
        p1.start()
        p1._memory.create_session("C3 cleanup in Aether", ["fix layout manager paths"])
        p1.stop()

        captured = []
        container.resolve("event_bus").subscribe("memory.session.restored", lambda e: captured.append(e))
        p2 = MemoryPlugin()
        p2._db_path = db_path
        p2.initialize(container)
        p2.start()
        assert len(captured) >= 1
        assert captured[-1].payload["session"]["summary"] == "C3 cleanup in Aether"
        p2.stop()

    def test_start_no_event_when_no_session(self, container, db_path):
        captured = []
        container.resolve("event_bus").subscribe("memory.session.restored", lambda e: captured.append(e))
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        assert captured == []
        p.stop()


class TestMemoryContinueCommand:
    def test_continue_no_session_guides_user(self, plugin):
        cmd = Command(name="memory.continue", source="test", params={})
        result = plugin._handle_continue(cmd)
        assert "No work session found" in result["message"]

    def test_continue_reconstructs_with_summary_and_facts(self, plugin):
        plugin._memory.create_session(
            "C3 cleanup in the Aether repo",
            ["Need to fix layout manager paths in aether/ui/panel/layout_manager.py"],
        )
        cmd = Command(name="memory.continue", source="test", params={})
        result = plugin._handle_continue(cmd)
        msg = result["message"]
        assert "You were working on C3 cleanup in the Aether repo." in msg
        assert "Need to fix layout manager paths" in msg
        assert "Ready to continue." in msg

    def test_continue_reconstructs_without_facts(self, plugin):
        plugin._memory.create_session("Refactor the repository")
        cmd = Command(name="memory.continue", source="test", params={})
        result = plugin._handle_continue(cmd)
        assert "You were working on Refactor the repository." in result["message"]
        assert "Ready to continue." in result["message"]

    def test_continue_with_summary_starts_session(self, plugin):
        cmd = Command(
            name="memory.continue", source="test",
            params={"summary": "Fix the layout manager paths"},
        )
        result = plugin._handle_continue(cmd)
        assert "New work session started" in result["message"]
        session = plugin._memory.get_latest_session()
        assert session["summary"] == "Fix the layout manager paths"

    def test_continue_with_fact_appends(self, plugin):
        plugin._memory.create_session("Refactor the repository")
        cmd = Command(
            name="memory.continue", source="test",
            params={"fact": "Needs WAL mode"},
        )
        result = plugin._handle_continue(cmd)
        assert result["message"] == "Remembered: Needs WAL mode"
        assert plugin._memory.get_latest_session()["key_facts"] == ["Needs WAL mode"]

    def test_continue_with_fact_starts_session_when_none(self, plugin):
        cmd = Command(
            name="memory.continue", source="test",
            params={"fact": "First thing to track"},
        )
        result = plugin._handle_continue(cmd)
        assert "New work session started" in result["message"]
        session = plugin._memory.get_latest_session()
        assert session["summary"] == "First thing to track"

    def test_continue_registered_in_command_bus(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        cmd_bus = container.resolve("command_bus")
        assert cmd_bus.is_registered("memory.continue")

    def test_continue_survives_restart(self, container, db_path):
        p1 = MemoryPlugin()
        p1._db_path = db_path
        p1.initialize(container)
        p1.start()
        p1._memory.create_session(
            "Continue C3 work",
            ["rewire theme_manager seeds"],
        )
        p1.stop()

        p2 = MemoryPlugin()
        p2._db_path = db_path
        p2.initialize(container)
        p2.start()
        cmd = Command(name="memory.continue", source="test", params={})
        result = p2._handle_continue(cmd)
        assert "You were working on Continue C3 work." in result["message"]
        assert "rewire theme_manager seeds" in result["message"]
        p2.stop()

    def test_continue_does_not_affect_seeded_semantic_count(self, plugin):
        before = plugin._memory.count("semantic")
        plugin._memory.create_session("New task")
        plugin._memory.append_session_fact("a fact")
        assert plugin._memory.count("semantic") == before == SEED_COUNT
        assert plugin._memory.count("working") == 1