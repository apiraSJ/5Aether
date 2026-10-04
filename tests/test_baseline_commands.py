"""Tests for BaselinePlugin — lifecycle, commands, EventBus integration (M1)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import EventBus
from aether.core.frame_broker import FrameBroker
from aether.core.service_container import ServiceContainer
from aether.memory.memory_manager import MemoryManager
from aether.plugins.baseline_plugin import BaselinePlugin
from aether.sandbox.catalog import COMPONENTS


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "baseline.db")


@pytest.fixture
def snapshots_dir(tmp_path):
    return str(tmp_path)


class _FakeConfig:
    """Minimal config stub exposing the dotted get() used by plugins."""

    def __init__(self, data):
        self._data = data

    def get(self, key_path, default=None):
        value = self._data
        for part in key_path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value


@pytest.fixture
def container(db_path, snapshots_dir):
    c = ServiceContainer()
    c.register_instance("event_bus", EventBus(queued=False))
    c.register_instance("command_bus", CommandBus())
    c.register_instance("config", _FakeConfig({"baseline": {"snapshots_dir": snapshots_dir}}))
    memory = MemoryManager(db_path=db_path)
    memory.open()
    c.register_instance("memory_manager", memory)
    broker = FrameBroker(event_bus=c.resolve("event_bus"))
    c.register_instance("frame_broker", broker)
    yield c
    memory.close()


@pytest.fixture
def plugin(container, snapshots_dir):
    p = BaselinePlugin()
    p.initialize(container)
    p.start()
    yield p
    try:
        p.stop()
    except Exception:
        pass


def _frame(height=48, width=64):
    return np.zeros((height, width, 3), dtype=np.uint8)


class TestBaselineLifecycle:
    def test_name(self):
        assert BaselinePlugin.name == "baseline_plugin"

    def test_initialize_registers_service_and_commands(self, container):
        p = BaselinePlugin()
        p.initialize(container)
        assert container.has("baseline_service")
        assert p.service is not None
        registry = container.resolve("command_registry")
        for cmd in ("baseline.select", "baseline.capture", "baseline.status", "baseline.list"):
            assert registry.is_registered(cmd)

    def test_start_seeds_catalog(self, plugin, container):
        memory = container.resolve("memory_manager")
        for comp in COMPONENTS:
            assert memory.recall(f"component:{comp['id']}", "working").found

    def test_metadata_lists_commands(self, container):
        p = BaselinePlugin()
        p.initialize(container)
        assert p.metadata.label == "Baseline"
        assert "baseline.capture" in p.metadata.commands

    def test_initialize_without_frame_broker(self, container):
        container.unregister("frame_broker")
        p = BaselinePlugin()
        p.initialize(container)
        assert p._frame_broker is None


class TestBaselineSelect:
    def test_select_publishes_event_and_message(self, plugin, container):
        event_bus = container.resolve("event_bus")
        captured = []
        event_bus.subscribe("baseline.selected", lambda e: captured.append(e.payload))
        cmd = Command(name="baseline.select", source="test", params={"component_id": "1"})
        result = container.resolve("command_bus").dispatch_sync(cmd)
        assert "Circuit Breaker" in result["message"]
        assert captured and captured[0]["component_id"] == "1"

    def test_select_unknown_component(self, plugin, container):
        cmd = Command(name="baseline.select", source="test", params={"component_id": "9"})
        result = container.resolve("command_bus").dispatch_sync(cmd)
        assert "Unknown component" in result["message"]


class TestBaselineCapture:
    def test_capture_writes_snapshot_and_publishes(self, plugin, container):
        event_bus = container.resolve("event_bus")
        captured = []
        event_bus.subscribe("baseline.captured", lambda e: captured.append(e.payload))
        container.resolve("frame_broker").update_frame(_frame())

        cmd = Command(name="baseline.capture", source="test", params={"component_id": "2"})
        result = container.resolve("command_bus").dispatch_sync(cmd)
        assert "Backup Power Supply" in result["message"]
        assert ".png" in result["message"]
        assert captured and captured[0]["component_id"] == "2"

    def test_capture_without_frame_message(self, plugin, container):
        cmd = Command(name="baseline.capture", source="test", params={"component_id": "1"})
        result = container.resolve("command_bus").dispatch_sync(cmd)
        assert "No frame yet" in result["message"]

    def test_capture_without_broker_message(self, container):
        container.unregister("frame_broker")
        p = BaselinePlugin()
        p.initialize(container)
        cmd = Command(name="baseline.capture", source="test", params={"component_id": "1"})
        result = container.resolve("command_bus").dispatch_sync(cmd)
        assert "No camera available" in result["message"]


class TestBaselineListAndStatus:
    def test_status_message(self, plugin, container):
        cmd = Command(name="baseline.status", source="test")
        result = container.resolve("command_bus").dispatch_sync(cmd)
        assert "0/" in result["message"]

    def test_list_message_and_entries(self, plugin, container):
        cmd = Command(name="baseline.list", source="test")
        result = container.resolve("command_bus").dispatch_sync(cmd)
        assert "Baseline catalog" in result["message"]
        assert len(result["baselines"]) == len(COMPONENTS)

    def test_human_readable_default(self, plugin, container):
        cmd = Command(name="baseline.status", source="test")
        result = container.resolve("command_bus").dispatch_sync(cmd)
        assert isinstance(result, dict) and "message" in result