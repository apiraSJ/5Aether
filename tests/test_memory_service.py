"""Tests for MemoryService — the functional memory facade for the UI layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.core.event_bus_v2 import EventBus
from aether.memory.memory_manager import MemoryManager
from aether.memory.seed_data import DEMO_MEMORIES, SUGGESTIONS
from aether.services.memory_service import MemoryService


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "memory.db")


@pytest.fixture
def manager(db_path):
    m = MemoryManager(db_path=db_path)
    m.open()
    m.seed_if_empty()
    yield m
    m.close()


@pytest.fixture
def event_bus():
    return EventBus(queued=False)


@pytest.fixture
def service(manager, event_bus):
    return MemoryService(manager, event_bus=event_bus)


class TestMemoryServiceRecent:
    def test_recent_returns_seeded_records(self, service):
        items = service.recent(limit=10)
        assert len(items) == 10
        assert items[0]["title"]  # newest seeded record first

    def test_recent_limit(self, service):
        assert len(service.recent(limit=3)) == 3

    def test_recent_returns_view_dicts(self, service):
        items = service.recent(limit=1)
        item = items[0]
        for field in ("id", "title", "summary", "content", "tags",
                      "importance", "source", "pinned", "memory_type",
                      "created_at", "updated_at"):
            assert field in item


class TestMemoryServicePinned:
    def test_pinned_returns_pinned_only(self, service):
        items = service.pinned()
        assert len(items) == sum(1 for m in DEMO_MEMORIES if m["pinned"])
        assert all(i["pinned"] for i in items)

    def test_pin_toggle(self, service):
        unpinned = next(i for i in service.recent(limit=20) if not i["pinned"])
        assert service.set_pinned(unpinned["id"], True)
        view = service.recall(unpinned["id"])
        assert view["pinned"] is True
        assert service.set_pinned(unpinned["id"], False)
        view = service.recall(unpinned["id"])
        assert view["pinned"] is False


class TestMemoryServiceSearch:
    def test_search_gesture(self, service):
        results = service.search("gesture")
        assert results
        assert any("gesture" in (r["title"] + r["content"]).lower() for r in results)

    def test_search_camera(self, service):
        results = service.search("camera")
        assert results
        assert any("camera" in (r["title"] + r["content"]).lower() for r in results)

    def test_search_empty(self, service):
        assert service.search("") == []
        assert service.search("   ") == []

    def test_search_no_results(self, service):
        assert service.search("zzzzzzz") == []

    def test_search_suggestion_coverage(self, service):
        for suggestion in SUGGESTIONS:
            assert service.search(suggestion), f"no results for suggestion '{suggestion}'"


class TestMemoryServiceCRUD:
    def test_add(self, service):
        view = service.add({
            "title": "My custom memory",
            "summary": "Added through the service",
            "content": "Detailed content here.",
            "tags": ["test", "ui"],
            "importance": 5,
        })
        assert view is not None
        assert view["title"] == "My custom memory"
        assert view["tags"] == ["test", "ui"]
        assert view["importance"] == 5
        assert view["pinned"] is False

    def test_add_requires_title(self, service):
        assert service.add({"summary": "no title"}) is None

    def test_update(self, service):
        view = service.add({"title": "Before", "tags": ["a"]})
        assert service.update({"id": view["id"], "title": "After", "importance": 3})
        updated = service.recall(view["id"])
        assert updated["title"] == "After"
        assert updated["importance"] == 3
        assert updated["tags"] == ["a"]  # unmentioned fields preserved

    def test_update_missing_record(self, service):
        assert service.update({"id": "does-not-exist", "title": "x"}) is False

    def test_recall_roundtrip(self, service):
        view = service.add({"title": "Round trip", "content": "payload"})
        recalled = service.recall(view["id"])
        assert recalled == view

    def test_delete(self, service):
        view = service.add({"title": "Doomed"})
        assert service.delete(view["id"]) is True
        assert service.recall(view["id"]) is None
        assert service.delete(view["id"]) is False

    def test_stats(self, service):
        stats = service.stats()
        assert stats["semantic"] == len(DEMO_MEMORIES)
        assert stats["pinned"] == sum(1 for m in DEMO_MEMORIES if m["pinned"])
        assert stats["total"] == len(DEMO_MEMORIES)


class TestMemoryServiceEvents:
    def test_search_events(self, service, event_bus):
        captured = []

        def handler(event):
            captured.append(event)

        event_bus.subscribe("memory.search.requested", handler)
        event_bus.subscribe("memory.search.completed", handler)

        service.search("camera")

        types = [e.type for e in captured]
        assert "memory.search.requested" in types
        assert "memory.search.completed" in types

    def test_recall_events(self, service, event_bus):
        captured = []

        def handler(event):
            captured.append(event)

        event_bus.subscribe("memory.recall.requested", handler)
        event_bus.subscribe("memory.recall.completed", handler)

        item = service.recent(limit=1)[0]
        service.recall(item["id"])

        types = [e.type for e in captured]
        assert "memory.recall.requested" in types
        assert "memory.recall.completed" in types

    def test_crud_events(self, service, event_bus):
        captured = []

        def handler(event):
            captured.append(event)

        for t in ("memory.created", "memory.updated", "memory.pinned", "memory.unpinned", "memory.deleted"):
            event_bus.subscribe(t, handler)

        view = service.add({"title": "Eventful"})
        service.update({"id": view["id"], "title": "Eventful 2"})
        service.set_pinned(view["id"], True)
        service.set_pinned(view["id"], False)
        service.delete(view["id"])

        types = [e.type for e in captured]
        assert "memory.created" in types
        assert "memory.updated" in types
        assert "memory.pinned" in types
        assert "memory.unpinned" in types
        assert "memory.deleted" in types
