"""Tests for MemoryPlugin — lifecycle, command handlers, EventBus integration."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import Event, EventBus
from aether.core.service_container import ServiceContainer
from aether.memory.memory_manager import MemoryManager
from aether.memory.seed_data import DEMO_MEMORIES
from aether.plugins.memory_plugin import MemoryPlugin

SEED_COUNT = len(DEMO_MEMORIES)


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


class TestMemoryPluginLifecycle:
    def test_initialize_creates_memory_manager(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        assert p._memory is not None
        assert isinstance(p._memory, MemoryManager)
        assert container.has("memory_manager")

    def test_start_opens_db(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        assert not p._memory.is_open
        p.start()
        assert p._memory.is_open
        p.stop()

    def test_stop_closes_db(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        assert p._memory.is_open
        p.stop()
        assert not p._memory.is_open

    def test_stop_unsubscribes_from_events(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        event_bus = container.resolve("event_bus")
        count_before = event_bus.get_subscriber_count("vision.object.detected")
        assert count_before >= 1
        p.stop()
        count_after = event_bus.get_subscriber_count("vision.object.detected")
        assert count_after == 0

    def test_metadata(self, container):
        p = MemoryPlugin()
        m = p.metadata
        assert m.label == "Memory"
        assert m.version == "1.0"
        assert "memory.recall" in m.commands

    def test_name(self):
        assert MemoryPlugin.name == "memory_plugin"


class TestMemoryPluginCommands:
    def test_recall_not_found(self, plugin):
        cmd = Command(name="memory.recall", source="test", params={"key": "nonexistent"})
        result = plugin._handle_recall(cmd)
        assert "not found" in result["message"]

    def test_recall_empty_key(self, plugin):
        cmd = Command(name="memory.recall", source="test", params={"key": ""})
        result = plugin._handle_recall(cmd)
        assert "Usage" in result["message"]

    def test_recall_found(self, plugin):
        plugin._memory.store("semantic", "testkey", {"value": 42})
        cmd = Command(name="memory.recall", source="test", params={"key": "testkey"})
        result = plugin._handle_recall(cmd)
        assert "Found" in result["message"]
        assert "testkey" in result["message"]

    def test_recall_with_type(self, plugin):
        plugin._memory.store("semantic", "bottle", {"color": "blue"})
        cmd = Command(name="memory.recall", source="test", params={"key": "bottle", "type": "semantic"})
        result = plugin._handle_recall(cmd)
        assert "Found" in result["message"]

    def test_recall_spatial_with_position(self, plugin):
        plugin._memory.store("spatial", "bottle", x=1.0, y=2.0, z=0.0, label="bottle", confidence=0.95)
        cmd = Command(name="memory.recall", source="test", params={"key": "bottle"})
        result = plugin._handle_recall(cmd)
        assert "Found" in result["message"]
        assert "position" in result["message"]

    def test_remember_stores_value(self, plugin):
        cmd = Command(
            name="memory.remember", source="test",
            params={"key": "bottle", "value": '{"location": "desk"}'},
        )
        result = plugin._handle_remember(cmd)
        assert "Stored" in result["message"]
        assert "bottle" in result["message"]

        recall = plugin._memory.recall("bottle")
        assert recall.found
        assert recall.records[0].value == {"location": "desk"}

    def test_remember_empty_key(self, plugin):
        cmd = Command(name="memory.remember", source="test", params={"key": "", "value": "test"})
        result = plugin._handle_remember(cmd)
        assert "Usage" in result["message"]

    def test_remember_default_type(self, plugin):
        cmd = Command(
            name="memory.remember", source="test",
            params={"key": "testkey", "value": '"hello"'},
        )
        plugin._handle_remember(cmd)
        recall = plugin._memory.recall("testkey")
        assert recall.records[0].memory_type == "semantic"

    def test_forget_deletes(self, plugin):
        plugin._memory.store("semantic", "bottle", {"color": "blue"})
        cmd = Command(name="memory.forget", source="test", params={"key": "bottle"})
        result = plugin._handle_forget(cmd)
        assert "Deleted" in result["message"]

        recall = plugin._memory.recall("bottle")
        assert not recall.found

    def test_forget_empty_key(self, plugin):
        cmd = Command(name="memory.forget", source="test", params={"key": ""})
        result = plugin._handle_forget(cmd)
        assert "Usage" in result["message"]

    def test_list_empty(self, plugin):
        cmd = Command(name="memory.list", source="test")
        result = plugin._handle_list(cmd)
        assert f"{SEED_COUNT} keys" in result["message"]
        assert "sprint-1.5" in result["message"]

    def test_list_with_records(self, plugin):
        plugin._memory.store("semantic", "bottle")
        plugin._memory.store("semantic", "keys")
        cmd = Command(name="memory.list", source="test")
        result = plugin._handle_list(cmd)
        assert "2 keys" in result["message"]
        assert "bottle" in result["message"]
        assert "keys" in result["message"]

    def test_search_found(self, plugin):
        plugin._memory.store("semantic", "bottle", {"location": "kitchen counter"})
        cmd = Command(name="memory.search", source="test", params={"query": "kitchen"})
        result = plugin._handle_search(cmd)
        assert "result" in result["message"]
        assert "bottle" in result["message"]

    def test_search_not_found(self, plugin):
        cmd = Command(name="memory.search", source="test", params={"query": "zzzzz"})
        result = plugin._handle_search(cmd)
        assert "No results" in result["message"]

    def test_search_empty_query(self, plugin):
        cmd = Command(name="memory.search", source="test", params={"query": ""})
        result = plugin._handle_search(cmd)
        assert "Usage" in result["message"]

    def test_stats(self, plugin):
        plugin._memory.store("semantic", "bottle")
        plugin._memory.store("episodic", "event1")
        cmd = Command(name="memory.stats", source="test")
        result = plugin._handle_stats(cmd)
        assert "Memory Stats" in result["message"]
        assert "Semantic:" in result["message"]
        assert "Episodic:" in result["message"]
        assert "Total:" in result["message"]

    def test_expire(self, plugin):
        plugin._memory.store("working", "temp", ttl_seconds=0.0)
        cmd = Command(name="memory.expire", source="test")
        result = plugin._handle_expire(cmd)
        assert "Expired" in result["message"]

    def test_handler_registration(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        cmd_bus = container.resolve("command_bus")
        assert cmd_bus.is_registered("memory.recall")
        assert cmd_bus.is_registered("memory.remember")
        assert cmd_bus.is_registered("memory.forget")
        assert cmd_bus.is_registered("memory.list")
        assert cmd_bus.is_registered("memory.search")
        assert cmd_bus.is_registered("memory.stats")
        assert cmd_bus.is_registered("memory.expire")


class TestMemoryPluginEventSubscription:
    def test_subscribes_to_vision_events(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        event_bus = container.resolve("event_bus")
        assert event_bus.get_subscriber_count("vision.object.detected") >= 1

    def test_vision_object_detected_stores_spatial(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        event_bus = container.resolve("event_bus")

        event = Event(
            type="vision.object.detected",
            payload={
                "objects": [
                    {
                        "label": "bottle",
                        "confidence": 0.95,
                        "bbox": {"x1": 100, "y1": 200, "x2": 150, "y2": 250},
                    },
                    {
                        "label": "cup",
                        "confidence": 0.85,
                        "bbox": {"x1": 300, "y1": 400, "x2": 350, "y2": 450},
                    },
                ],
            },
        )
        event_bus.publish(event)

        recall = p._memory.recall("bottle")
        assert recall.found
        assert recall.records[0].label == "bottle"
        assert recall.records[0].confidence == 0.95
        assert hasattr(recall.records[0], "x")

        recall_cup = p._memory.recall("cup")
        assert recall_cup.found

        p.stop()

    def test_vision_event_no_objects(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        event_bus = container.resolve("event_bus")

        event = Event(type="vision.object.detected", payload={"objects": []})
        event_bus.publish(event)

        assert p._memory.count() == SEED_COUNT
        p.stop()

    def test_vision_event_without_bbox(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        event_bus = container.resolve("event_bus")

        event = Event(
            type="vision.object.detected",
            payload={
                "objects": [
                    {"label": "unknown", "confidence": 0.5, "bbox": {}},
                ],
            },
        )
        event_bus.publish(event)

        recall = p._memory.recall("unknown")
        assert recall.found
        p.stop()

    def test_does_not_store_when_not_opened(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)

        # Open and close DB to verify it starts with seeded demo data
        p.start()
        assert p._memory.count() == SEED_COUNT
        p.stop()

        event_bus = container.resolve("event_bus")
        event = Event(
            type="vision.object.detected",
            payload={
                "objects": [
                    {"label": "bottle", "confidence": 0.9, "bbox": {"x1": 0, "y1": 0, "x2": 10, "y2": 10}},
                ],
            },
        )
        event_bus.publish(event)

        # Reopen to verify nothing was stored
        p.start()
        assert p._memory.count() == SEED_COUNT
        p.stop()


class TestMemoryPluginBusPublishing:
    def test_store_emits_event(self, container, db_path):
        captured = []

        def handler(event):
            captured.append(event)

        event_bus = container.resolve("event_bus")
        event_bus.subscribe("memory.semantic.created", handler)

        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        p._memory.store("semantic", "bottle", {"color": "blue"})

        assert len(captured) >= 1
        assert captured[0].payload["key"] == "bottle"
        p.stop()

    def test_search_emits_event(self, container, db_path):
        captured = []

        def handler(event):
            captured.append(event)

        event_bus = container.resolve("event_bus")
        event_bus.subscribe("memory.query.completed", handler)

        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        p._memory.store("semantic", "bottle", {"location": "kitchen"})
        p._memory.search("kitchen")

        assert len(captured) >= 1
        assert captured[0].payload["query"] == "kitchen"
        p.stop()

    def test_spatial_query_emits_event(self, container, db_path):
        captured = []

        def handler(event):
            captured.append(event)

        event_bus = container.resolve("event_bus")
        event_bus.subscribe("memory.spatial.queried", handler)

        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        p._memory.store("spatial", "bottle", x=0.0, y=0.0, z=0.0, label="bottle")
        p._memory.recall_nearby(0.0, 0.0, 0.0)

        assert len(captured) >= 1
        assert captured[0].payload["found"] is True
        p.stop()

    def test_forget_emits_event(self, container, db_path):
        captured = []

        def handler(event):
            captured.append(event)

        event_bus = container.resolve("event_bus")
        event_bus.subscribe("memory.deleted", handler)

        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        p._memory.store("semantic", "bottle", {"color": "blue"})
        p._memory.forget("bottle")

        assert len(captured) >= 1
        assert captured[0].payload["key"] == "bottle"
        p.stop()

    def test_update_emits_event(self, container, db_path):
        captured = []

        def handler(event):
            captured.append(event)

        event_bus = container.resolve("event_bus")
        event_bus.subscribe("memory.updated", handler)

        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        aid = p._memory.store("semantic", "bottle", {"color": "blue"})
        p._memory.update(aid, value={"color": "red"})

        assert len(captured) >= 1
        assert captured[0].payload["id"] == aid
        p.stop()


class TestMemoryPluginSeeding:
    def test_start_seeds_demo_data(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        assert p._memory.count() == SEED_COUNT
        assert p._memory.list_pinned().total == sum(1 for m in DEMO_MEMORIES if m["pinned"])
        p.stop()

    def test_seed_is_idempotent(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        first = p._memory.count()
        seeded_again = p._memory.seed_if_empty()
        assert seeded_again == 0
        assert p._memory.count() == first
        p.stop()

    def test_seed_skipped_when_store_not_empty(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        p._memory.store("semantic", "user-fact", {"location": "desk"})
        # New manager on the same DB must not seed over user data
        p2 = MemoryPlugin()
        p2._db_path = db_path
        p2.initialize(container)
        p2.start()
        assert p2._memory.count() == SEED_COUNT + 1
        p.stop()
        p2.stop()

    def test_start_publishes_memory_ready(self, container, db_path):
        captured = []

        def handler(event):
            captured.append(event)

        event_bus = container.resolve("event_bus")
        event_bus.subscribe("memory.ready", handler)

        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        p.start()
        assert len(captured) >= 1
        assert captured[0].payload["seeded"] == SEED_COUNT
        p.stop()

    def test_registers_memory_service_in_container(self, container, db_path):
        p = MemoryPlugin()
        p._db_path = db_path
        p.initialize(container)
        assert container.has("memory_service")
        service = container.resolve("memory_service")
        assert service is not None
        p.stop()
