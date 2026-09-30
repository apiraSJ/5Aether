"""Tests for Aether Memory Core — MemoryManager, SQLiteRepository, models.

Tests cover:
    - MemoryRecord/SpatialRecord model validation
    - SQLiteRepository CRUD (store, recall, update, forget)
    - FTS5 full-text search
    - R-Tree spatial queries
    - TTL expiration
    - MemoryManager public API
    - MemoryPlugin command handlers
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from aether.memory.models import (
    MemoryRecord,
    MemoryType,
    QueryFilter,
    RecallResult,
    SpatialRecord,
)
from aether.memory.sqlite_repository import SQLiteRepository
from aether.memory.memory_manager import MemoryManager


# ── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "test_memory.db")


@pytest.fixture
def repo(db_path):
    """Create a SQLiteRepository with a temporary database."""
    r = SQLiteRepository(db_path)
    r.open()
    yield r
    r.close()


@pytest.fixture
def memory_manager(db_path):
    """Create a MemoryManager with a temporary database."""
    mm = MemoryManager(db_path=db_path)
    mm.open()
    yield mm
    mm.close()


# ── Model Tests ────────────────────────────────────────────────────

class TestMemoryRecord:
    def test_create(self):
        record = MemoryRecord(
            id="test-id", memory_type="semantic", key="bottle",
            value={"location": "desk"}, created_at=100.0, updated_at=100.0,
        )
        assert record.id == "test-id"
        assert record.key == "bottle"
        assert record.value == {"location": "desk"}

    def test_is_expired_with_ttl(self):
        record = MemoryRecord(
            id="t1", memory_type="working", key="temp",
            created_at=time.perf_counter() - 100,  # 100s old
            updated_at=time.perf_counter() - 100,
            ttl_seconds=50.0,  # 50s TTL
        )
        assert record.is_expired

    def test_not_expired_without_ttl(self):
        record = MemoryRecord(
            id="t2", memory_type="semantic", key="perm",
            created_at=time.perf_counter() - 100000,
            updated_at=time.perf_counter() - 100000,
            ttl_seconds=None,
        )
        assert not record.is_expired

    def test_access_count(self):
        record = MemoryRecord(
            id="t3", memory_type="semantic", key="test",
            access_count=5, created_at=0, updated_at=0,
        )
        assert record.access_count == 5


class TestSpatialRecord:
    def test_create(self):
        record = SpatialRecord(
            id="s1", memory_type="spatial", key="bottle",
            x=1.0, y=2.0, z=0.5, confidence=0.95, label="bottle",
            created_at=100.0, updated_at=100.0,
        )
        assert record.x == 1.0
        assert record.y == 2.0
        assert record.label == "bottle"
        assert record.confidence == 0.95


class TestRecallResult:
    def test_not_found(self):
        result = RecallResult.not_found(query_time_ms=1.0)
        assert not result.found
        assert result.total == 0

    def test_error_result(self):
        result = RecallResult.error_result("DB error")
        assert not result.found
        assert result.error == "DB error"

    def test_found_with_records(self):
        records = [MemoryRecord(
            id="r1", memory_type="semantic", key="test",
            created_at=0, updated_at=0,
        )]
        result = RecallResult(found=True, records=records, total=1)
        assert result.found
        assert len(result.records) == 1


# ── SQLiteRepository Tests ─────────────────────────────────────────

class TestSQLiteRepository:
    def test_store_and_recall(self, repo):
        aid = repo.store(MemoryType.SEMANTIC, "bottle", {"location": "desk"})
        assert aid is not None
        assert len(aid) > 0

        result = repo.recall("bottle", MemoryType.SEMANTIC)
        assert result.found
        assert result.total == 1
        assert result.records[0].key == "bottle"
        assert result.records[0].value == {"location": "desk"}

    def test_recall_not_found(self, repo):
        result = repo.recall("nonexistent")
        assert not result.found
        assert result.total == 0

    def test_store_spatial(self, repo):
        aid = repo.store(
            MemoryType.SPATIAL, "bottle", {"color": "blue"},
            x=1.0, y=2.0, z=0.0, confidence=0.95, label="bottle",
        )
        assert aid is not None

        result = repo.recall("bottle", MemoryType.SPATIAL)
        assert result.found
        record = result.records[0]
        assert hasattr(record, "x")

    def test_recall_nearby(self, repo):
        # Store objects at different positions
        repo.store(MemoryType.SPATIAL, "bottle", x=0.0, y=0.0, z=0.0, label="bottle")
        repo.store(MemoryType.SPATIAL, "cup", x=1.0, y=1.0, z=0.0, label="cup")
        repo.store(MemoryType.SPATIAL, "book", x=10.0, y=10.0, z=0.0, label="book")

        # Query near origin with 2m radius
        result = repo.recall_nearby(0.0, 0.0, 0.0, radius_meters=2.0)
        assert result.found
        assert result.total >= 2  # bottle + cup
        for r in result.records:
            assert r.key in ("bottle", "cup")

    def test_recall_nearby_with_label(self, repo):
        repo.store(MemoryType.SPATIAL, "bottle", x=0.5, y=0.5, z=0.0, label="bottle")
        repo.store(MemoryType.SPATIAL, "cup", x=1.0, y=1.0, z=0.0, label="cup")

        result = repo.recall_nearby(0.0, 0.0, 0.0, radius_meters=5.0, label="bottle")
        assert result.found
        assert result.total == 1
        assert result.records[0].label == "bottle"

    def test_fts_search(self, repo):
        repo.store(MemoryType.SEMANTIC, "bottle", {"location": "kitchen counter"})
        repo.store(MemoryType.SEMANTIC, "keys", {"location": "desk drawer"})
        repo.store(MemoryType.SEMANTIC, "phone", {"location": "bedside table"})

        result = repo.search("kitchen")
        assert result.found
        assert result.total >= 1
        assert any(r.key == "bottle" for r in result.records)

    def test_fts_search_not_found(self, repo):
        result = repo.search("zzzzz")
        assert not result.found

    def test_update(self, repo):
        aid = repo.store(MemoryType.SEMANTIC, "bottle", {"location": "desk"})

        success = repo.update(aid, value={"location": "kitchen"})
        assert success

        result = repo.recall("bottle", MemoryType.SEMANTIC)
        assert result.records[0].value == {"location": "kitchen"}

    def test_forget(self, repo):
        repo.store(MemoryType.SEMANTIC, "bottle", {"location": "desk"})
        repo.store(MemoryType.SEMANTIC, "bottle", {"color": "blue"})

        count = repo.forget("bottle", MemoryType.SEMANTIC)
        assert count == 2

        result = repo.recall("bottle", MemoryType.SEMANTIC)
        assert not result.found

    def test_count(self, repo):
        assert repo.count() == 0
        repo.store(MemoryType.SEMANTIC, "bottle")
        repo.store(MemoryType.EPISODIC, "event1")
        repo.store(MemoryType.SPATIAL, "cup", x=0, y=0, z=0)
        assert repo.count() == 3
        assert repo.count(MemoryType.SEMANTIC) == 1
        assert repo.count(MemoryType.SPATIAL) == 1

    def test_list_keys(self, repo):
        repo.store(MemoryType.SEMANTIC, "bottle")
        repo.store(MemoryType.SEMANTIC, "keys")
        repo.store(MemoryType.EPISODIC, "event1")

        keys = repo.list_keys()
        assert "bottle" in keys
        assert "keys" in keys
        assert "event1" in keys

    def test_expire_stale(self, repo):
        # Store record with 0 TTL (immediately expired)
        repo.store(MemoryType.WORKING, "temp1", ttl_seconds=0.0)
        # Store record with long TTL
        repo.store(MemoryType.WORKING, "temp2", ttl_seconds=3600.0)

        count = repo.expire_stale()
        assert count >= 1

        result = repo.recall("temp1", MemoryType.WORKING)
        assert not result.found

    def test_store_recall_different_types(self, repo):
        repo.store(MemoryType.SEMANTIC, "bottle", {"location": "desk"})
        repo.store(MemoryType.SPATIAL, "bottle", x=1.0, y=2.0, z=0.0, label="bottle")

        # Recall all types
        result = repo.recall("bottle")
        assert result.total == 2  # one semantic + one spatial

        # Recall specific type
        result = repo.recall("bottle", MemoryType.SEMANTIC)
        assert result.total == 1

    def test_vacuum(self, repo):
        repo.store(MemoryType.SEMANTIC, "test")
        repo.forget("test")
        # Should not raise
        repo.vacuum()

    def test_close(self, repo):
        repo.close()
        assert not repo.is_open
        # Re-open should work
        repo.open()
        assert repo.is_open


# ── MemoryManager Tests ────────────────────────────────────────────

class TestMemoryManager:
    def test_store_and_recall(self, memory_manager):
        aid = memory_manager.store("semantic", "bottle", {"location": "desk"})
        assert aid is not None

        result = memory_manager.recall("bottle")
        assert result.found
        assert result.records[0].value == {"location": "desk"}

    def test_store_spatial(self, memory_manager):
        aid = memory_manager.store(
            "spatial", "bottle", {"color": "blue"},
            x=1.0, y=2.0, z=0.0, confidence=0.95, label="bottle",
        )
        assert aid is not None

        result = memory_manager.recall("bottle", "spatial")
        assert result.found

    def test_recall_nearby(self, memory_manager):
        memory_manager.store("spatial", "bottle", x=0.0, y=0.0, z=0.0, label="bottle")
        memory_manager.store("spatial", "cup", x=1.0, y=1.0, z=0.0, label="cup")

        result = memory_manager.recall_nearby(0.0, 0.0, 0.0, radius_meters=2.0)
        assert result.found
        assert result.total >= 2

    def test_search(self, memory_manager):
        memory_manager.store("semantic", "bottle", {"location": "kitchen counter"})
        memory_manager.store("semantic", "keys", {"location": "desk"})

        result = memory_manager.search("kitchen")
        assert result.found

    def test_forget(self, memory_manager):
        memory_manager.store("semantic", "bottle")
        memory_manager.store("episodic", "event1")

        count = memory_manager.forget("bottle")
        assert count >= 1

        result = memory_manager.recall("bottle")
        assert not result.found

        # Other records remain
        result = memory_manager.recall("event1")
        assert result.found

    def test_count(self, memory_manager):
        assert memory_manager.count() == 0
        memory_manager.store("semantic", "bottle")
        memory_manager.store("episodic", "event1")
        assert memory_manager.count() == 2
        assert memory_manager.count("semantic") == 1

    def test_list_keys(self, memory_manager):
        memory_manager.store("semantic", "bottle")
        memory_manager.store("semantic", "keys")

        keys = memory_manager.list_keys()
        assert "bottle" in keys
        assert "keys" in keys

    def test_invalid_memory_type(self, memory_manager):
        with pytest.raises(ValueError, match="Unknown memory type"):
            memory_manager.store("invalid_type", "test")

    def test_closed_manager_raises(self):
        mm = MemoryManager(db_path=":memory:")
        # Not opened - should raise
        with pytest.raises(RuntimeError):
            mm.recall("test")

    def test_expire_stale(self, memory_manager):
        memory_manager.store("working", "temp1", ttl_seconds=0.0)
        memory_manager.store("working", "temp2", ttl_seconds=3600.0)

        count = memory_manager.expire_stale()
        assert count >= 1

    def test_update(self, memory_manager):
        aid = memory_manager.store("semantic", "bottle", {"location": "desk"})
        success = memory_manager.update(aid, value={"location": "kitchen"})
        assert success

        result = memory_manager.recall("bottle")
        assert result.records[0].value == {"location": "kitchen"}


# ── Seed (Sprint 2.1A) ───────────────────────────────────────────────


class TestSeedIfEmpty:
    def test_seeds_on_empty_store(self, memory_manager):
        from aether.memory.seed_data import DEMO_MEMORIES

        seeded = memory_manager.seed_if_empty()
        assert seeded == len(DEMO_MEMORIES)
        assert memory_manager.count() == len(DEMO_MEMORIES)

    def test_seed_sets_metadata(self, memory_manager):
        from aether.memory.seed_data import DEMO_MEMORIES

        memory_manager.seed_if_empty()
        result = memory_manager.list_recent(limit=20)
        record = next(r for r in result.records if r.context.get("title"))
        assert record.context["title"]
        assert record.context["tags"]
        assert record.context["content"]
        assert "importance" in record.context
        assert "source" in record.context
        assert "pinned" in record.context

    def test_seed_idempotent(self, memory_manager):
        from aether.memory.seed_data import DEMO_MEMORIES

        first = memory_manager.seed_if_empty()
        second = memory_manager.seed_if_empty()
        assert first == len(DEMO_MEMORIES)
        assert second == 0

    def test_seed_skipped_when_user_data_exists(self, memory_manager):
        memory_manager.store("semantic", "user-fact", {"k": "v"})
        assert memory_manager.seed_if_empty() == 0

    def test_seed_creates_aged_records(self, memory_manager):
        memory_manager.seed_if_empty()
        recent = memory_manager.list_recent(limit=20).records
        newest = max(r.created_at for r in recent)
        assert newest < time.time()  # seeded in the past, not "now"

    def test_seed_searchable(self, memory_manager):
        memory_manager.seed_if_empty()
        result = memory_manager.search("camera")
        assert result.found

    def test_pinned_repository_query(self, memory_manager):
        memory_manager.seed_if_empty()
        pinned = memory_manager.list_pinned()
        assert pinned.total > 0
        assert all(r.context.get("pinned") for r in pinned.records)

    def test_get_delete_by_id(self, memory_manager):
        memory_manager.seed_if_empty()
        record = memory_manager.list_recent(limit=1).records[0]
        fetched = memory_manager.get(record.id)
        assert fetched is not None
        assert fetched.id == record.id
        assert memory_manager.delete(record.id) is True
        assert memory_manager.get(record.id) is None
        assert memory_manager.delete(record.id) is False

    def test_set_pinned(self, memory_manager):
        memory_manager.seed_if_empty()
        unpinned = next(
            r for r in memory_manager.list_recent(limit=20).records
            if not r.context.get("pinned")
        )
        assert memory_manager.set_pinned(unpinned.id, True) is True
        updated = memory_manager.get(unpinned.id)
        assert updated.context["pinned"] is True
        assert memory_manager.set_pinned(unpinned.id, False) is True
        assert memory_manager.get(unpinned.id).context["pinned"] is False

