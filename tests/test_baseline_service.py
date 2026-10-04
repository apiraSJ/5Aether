"""Tests for BaselineService — seed / capture / list via MemoryManager (M1)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from aether.baseline.baseline_service import (
    BaselineService,
    SNAPSHOT_SUBDIR,
    component_key,
)
from aether.memory.memory_manager import MemoryManager
from aether.sandbox.catalog import COMPONENTS


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "baseline.db")


@pytest.fixture
def snapshots_dir(tmp_path):
    return str(tmp_path)


@pytest.fixture
def memory(db_path):
    mm = MemoryManager(db_path=db_path)
    mm.open()
    yield mm
    mm.close()


@pytest.fixture
def service(memory, snapshots_dir):
    return BaselineService(memory, snapshots_dir=snapshots_dir)


def _frame(height=48, width=64):
    return np.zeros((height, width, 3), dtype=np.uint8)


class TestSeedCatalog:
    def test_seed_registers_every_component_in_working_table(self, service):
        count = service.seed_catalog()
        assert count == len(COMPONENTS)
        for comp in COMPONENTS:
            result = service._memory.recall(component_key(comp["id"]), "working")
            assert result.found
            record = result.records[0]
            assert record.memory_type == "working"
            assert record.value["component_id"] == comp["id"]

    def test_seed_stores_metadata_without_snapshot(self, service):
        service.seed_catalog()
        result = service._memory.recall(component_key("1"), "working")
        assert result.records[0].value["snapshot_path"] is None
        assert result.records[0].value["captured_at"] is None

    def test_seed_is_idempotent(self, service, memory):
        service.seed_catalog()
        service.seed_catalog()
        keys = memory.list_keys("working")
        assert len(keys) >= len(COMPONENTS)


class TestCapture:
    def test_capture_writes_png_and_records_path(self, service, snapshots_dir):
        service.seed_catalog()
        value = service.capture("1", _frame())
        assert value is not None
        assert value["component_id"] == "1"
        assert value["snapshot_path"]
        assert value["captured_at"]
        assert value["width"] == 64
        assert value["height"] == 48

        path = Path(value["snapshot_path"])
        assert path.exists()
        assert path.name == "1.png"
        assert SNAPSHOT_SUBDIR in path.parts

    def test_capture_records_on_component_key(self, service, memory):
        service.seed_catalog()
        service.capture("1", _frame())
        result = memory.recall(component_key("1"), "working")
        assert result.found
        assert result.records[0].value["snapshot_path"]

    def test_capture_unknown_component_returns_none(self, service):
        assert service.capture("9", _frame()) is None

    def test_capture_none_frame_returns_none(self, service):
        service.seed_catalog()
        assert service.capture("1", None) is None


class TestListAndStatus:
    def test_list_baselines_initial_all_pending(self, service):
        service.seed_catalog()
        entries = service.list_baselines()
        assert len(entries) == len(COMPONENTS)
        assert all(e["captured"] is False for e in entries)
        assert entries[0]["component_id"] == "1"

    def test_list_marks_captured_after_snapshot(self, service):
        service.seed_catalog()
        service.capture("2", _frame())
        entries = service.list_baselines()
        by_id = {e["component_id"]: e for e in entries}
        assert by_id["2"]["captured"] is True
        assert by_id["1"]["captured"] is False

    def test_status_counts_seeded_and_captured(self, service):
        service.seed_catalog()
        service.capture("1", _frame())
        status = service.baseline_status()
        assert status["seeded"] == len(COMPONENTS)
        assert status["captured"] == 1