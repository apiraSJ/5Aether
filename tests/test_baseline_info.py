"""Tests for baseline.info — additive M2 query used by the voice 'แสดงข้อมูล' intent."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import EventBus
from aether.core.service_container import ServiceContainer
from aether.memory.memory_manager import MemoryManager
from aether.plugins.baseline_plugin import BaselinePlugin


class _FakeConfig:
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
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "baseline.db")


@pytest.fixture
def container(db_path, tmp_path):
    c = ServiceContainer()
    c.register_instance("event_bus", EventBus(queued=False))
    c.register_instance("command_bus", CommandBus())
    c.register_instance("config", _FakeConfig({"baseline": {"snapshots_dir": str(tmp_path)}}))
    memory = MemoryManager(db_path=db_path)
    memory.open()
    c.register_instance("memory_manager", memory)
    yield c
    memory.close()


@pytest.fixture
def plugin(container):
    p = BaselinePlugin()
    p.initialize(container)
    p.start()
    yield p


class TestBaselineInfo:
    def test_info_is_registered(self, container):
        BaselinePlugin().initialize(container)
        registry = container.resolve("command_registry")
        assert registry.is_registered("baseline.info")

    def test_info_returns_full_catalog_entry(self, plugin, container):
        command_bus = container.resolve("command_bus")
        result = command_bus.dispatch_sync(
            Command(name="baseline.info", source="test", params={"component_id": "2"})
        )
        assert "Backup Power Supply" in result["message"]
        comp = result["component"]
        assert comp["specifications"]["capacity"] == "2000 VA"
        assert "inspection_procedure" in comp
        assert "troubleshooting" in comp
        assert "source_manual" in comp

    def test_info_unknown_component(self, plugin, container):
        command_bus = container.resolve("command_bus")
        result = command_bus.dispatch_sync(
            Command(name="baseline.info", source="test", params={"component_id": "9"})
        )
        assert "Unknown component" in result["message"]

    def test_info_empty_id(self, plugin, container):
        command_bus = container.resolve("command_bus")
        result = command_bus.dispatch_sync(
            Command(name="baseline.info", source="test", params={"component_id": ""})
        )
        assert "Unknown component" in result["message"]

    def test_info_covers_all_components(self, plugin, container):
        command_bus = container.resolve("command_bus")
        from aether.sandbox.catalog import COMPONENTS

        for comp in COMPONENTS:
            result = command_bus.dispatch_sync(
                Command(name="baseline.info", source="test", params={"component_id": comp["id"]})
            )
            assert result["component"]["name"] == comp["name"]