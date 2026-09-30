"""Tests for MemoryController — pure-Python panel logic."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.core.event_bus_v2 import EventBus
from aether.memory.memory_manager import MemoryManager
from aether.services.memory_service import MemoryService
from aether.ui.panel.memory_controller import MemoryController
from aether.ui.panel.panel_session import PanelSession


@pytest.fixture
def service():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = MemoryManager(db_path=str(Path(tmpdir) / "memory.db"))
        manager.open()
        manager.seed_if_empty()
        yield MemoryService(manager, event_bus=EventBus(queued=False))
        manager.close()


@pytest.fixture
def controller(service):
    session = PanelSession(panel_id="memory", panel_type="memory")
    c = MemoryController(session, service=service)
    return c


class TestMemoryControllerActions:
    def test_search(self, controller):
        results = controller.handle_action("search", query="camera")
        assert results
        assert any("camera" in (r["title"] + r["content"]).lower() for r in results)

    def test_recent(self, controller):
        results = controller.handle_action("recent")
        assert len(results) == 10

    def test_pinned(self, controller):
        results = controller.handle_action("pinned")
        assert results
        assert all(r["pinned"] for r in results)

    def test_recall(self, controller):
        item = controller.handle_action("recent")[0]
        view = controller.handle_action("recall", id=item["id"])
        assert view is not None
        assert view["id"] == item["id"]

    def test_recall_unknown_id(self, controller):
        assert controller.handle_action("recall", id="missing") is None

    def test_pin_toggle(self, controller):
        item = next(r for r in controller.handle_action("recent", limit=20) if not r["pinned"])
        assert controller.handle_action("pin", id=item["id"]) is True
        view = controller.handle_action("recall", id=item["id"])
        assert view["pinned"] is True

    def test_delete(self, controller):
        item = controller.handle_action("recent")[0]
        assert controller.handle_action("delete", id=item["id"]) is True
        assert controller.handle_action("recall", id=item["id"]) is None

    def test_stats(self, controller):
        stats = controller.handle_action("stats")
        assert stats["total"] > 0

    def test_unknown_action(self, controller):
        assert controller.handle_action("nonsense") is None

    def test_focus_blur_are_noop(self, controller):
        assert controller.handle_action("focus") is None
        assert controller.handle_action("blur") is None


class TestMemoryControllerState:
    def test_session_state_roundtrip(self, controller):
        controller.set_state("last_query", "camera")
        assert controller.get_state("last_query") == "camera"
        assert controller.session.load_state("memory_query") is None

    def test_search_saves_session_state(self, controller):
        controller.handle_action("search", query="workspace")
        assert controller.session.load_state("memory_query") == "workspace"

    def test_recall_saves_session_state(self, controller):
        item = controller.handle_action("recent")[0]
        controller.handle_action("recall", id=item["id"])
        assert controller.session.load_state("memory_recall_id") == item["id"]


class TestMemoryControllerWithoutService:
    def test_actions_safe_without_service(self):
        session = PanelSession(panel_id="memory", panel_type="memory")
        controller = MemoryController(session, service=None)
        assert controller.handle_action("search", query="x") == []
        assert controller.handle_action("recent") == []
        assert controller.handle_action("pinned") == []
        assert controller.handle_action("recall", id="x") is None
        assert controller.handle_action("pin", id="x") is False
        assert controller.handle_action("delete", id="x") is False
        assert controller.handle_action("stats") == {}

    def test_wire_service_later(self, service):
        session = PanelSession(panel_id="memory", panel_type="memory")
        controller = MemoryController(session)
        assert controller.handle_action("recent") == []
        controller.wire_service(service)
        assert controller.handle_action("recent")
