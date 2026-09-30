"""End-to-end acceptance test for M1 Memory UX — "Continue my work".

Scenario:
    GIVEN the user has been working with Aether and recorded a work session
    WHEN Aether restarts
    THEN "Continue my work" reconstructs the context from memory, and the
         AI chat continues over that context — no re-explaining needed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import EventBus
from aether.core.service_container import ServiceContainer
from aether.plugins.ai_plugin import AIPlugin
from aether.plugins.memory_plugin import MemoryPlugin


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


def _boot_plugins(container, db_path):
    """Initialize + start fresh Memory and AI plugins on the given db."""
    mem = MemoryPlugin()
    mem._db_path = db_path
    ai = AIPlugin()
    mem.initialize(container)
    ai.initialize(container)
    mem.start()
    ai.start()
    return mem, ai


def _shutdown(mem, ai):
    try:
        ai.stop()
    finally:
        mem.stop()


class TestContinueMyWorkE2E:
    def test_work_session_survives_restart_and_reconstructs(self, container, db_path):
        bus = container.resolve("command_bus")

        # ── First run: user records their work context. ──
        mem1, ai1 = _boot_plugins(container, db_path)
        try:
            bus.dispatch_sync(Command(
                name="memory.continue", source="cli",
                params={"summary": "C3 cleanup in the Aether repo"},
            ))
            bus.dispatch_sync(Command(
                name="memory.continue", source="cli",
                params={"fact": "Need to fix layout manager paths in aether/ui/panel/layout_manager.py"},
            ))
        finally:
            _shutdown(mem1, ai1)

        # ── Restart: Aether stops, user returns. ──
        mem2, ai2 = _boot_plugins(container, db_path)
        try:
            # Boot restored the session into the AI service automatically.
            assert ai2._service._session_context is not None
            assert "C3 cleanup in the Aether repo" in ai2._service._session_context

            # "Continue my work" reconstructs the context without re-explaining.
            result = bus.dispatch_sync(Command(name="memory.continue", source="cli", params={}))
            msg = result["message"]
            assert "You were working on C3 cleanup in the Aether repo." in msg
            assert "Need to fix layout manager paths" in msg
            assert "Ready to continue." in msg

            # The AI chat continues over the reconstructed context.
            chat = bus.dispatch_sync(Command(
                name="ai.chat", source="cli",
                params={"message": "continue"},
            ))
            assert "continue" in chat["message"]
        finally:
            _shutdown(mem2, ai2)

    def test_workspace_memory_facts_remain_after_restart(self, container, db_path):
        bus = container.resolve("command_bus")

        mem1, ai1 = _boot_plugins(container, db_path)
        try:
            bus.dispatch_sync(Command(
                name="memory.remember", source="cli",
                params={"key": "task-c3", "value": "refactor seed paths", "type": "semantic"},
            ))
            bus.dispatch_sync(Command(
                name="memory.continue", source="cli",
                params={"summary": "Seed path refactor"},
            ))
        finally:
            _shutdown(mem1, ai1)

        mem2, ai2 = _boot_plugins(container, db_path)
        try:
            recall = bus.dispatch_sync(Command(
                name="memory.recall", source="cli",
                params={"key": "task-c3"},
            ))
            assert "task-c3" in recall["message"]

            reconstructed = bus.dispatch_sync(Command(
                name="memory.continue", source="cli", params={},
            ))
            assert "You were working on Seed path refactor." in reconstructed["message"]
            assert "Ready to continue." in reconstructed["message"]
        finally:
            _shutdown(mem2, ai2)