"""Contract tests for IMemoryService.

Every adapter that implements IMemoryService must pass these tests.

Run with: pytest tests/contracts/test_memory_service.py -v
"""

import pytest
from typing import Optional

from aether.domain.spatial_object import SpatialObject, SpatialRelation
from aether.domain.context_snapshot import ContextSnapshot
from aether.core.interfaces.i_memory_service import IMemoryService


class MemoryServiceContract:
    """Mixin class for memory service contract tests.

    Subclasses must set self.service in setup_method().
    """

    service: IMemoryService

    def setup_method(self):
        raise NotImplementedError

    # ── Remember ──────────────────────────────────────────────────

    def test_remember(self):
        obj = SpatialObject(name="laptop", position={"room": "desk"})
        record = self.service.remember(obj, source="gesture", intent="test")
        assert record is not None
        assert record.object.name == "laptop"
        assert record.source == "gesture"

    # ── Recall ────────────────────────────────────────────────────

    def test_recall_found(self):
        obj = SpatialObject(name="charger")
        self.service.remember(obj)
        result = self.service.recall("charger")
        assert result.found is True
        assert result.object.name == "charger"

    def test_recall_not_found(self):
        result = self.service.recall("nonexistent")
        assert result.found is False

    def test_recall_with_context(self):
        obj = SpatialObject(name="laptop")
        self.service.remember(obj)
        ctx = ContextSnapshot()
        result = self.service.recall("laptop", context=ctx)
        assert result.found is True

    # ── Forget ────────────────────────────────────────────────────

    def test_forget(self):
        obj = SpatialObject(name="temp_obj")
        self.service.remember(obj)
        assert self.service.forget("temp_obj") is True
        result = self.service.recall("temp_obj")
        assert result.found is False

    def test_forget_nonexistent(self):
        assert self.service.forget("nonexistent") is False

    # ── Associate ─────────────────────────────────────────────────

    def test_associate(self):
        laptop = SpatialObject(name="laptop")
        charger = SpatialObject(name="charger")
        self.service.remember(laptop)
        self.service.remember(charger)
        result = self.service.associate("laptop", "left_of", "charger")
        assert result is True

    def test_associate_nonexistent(self):
        result = self.service.associate("ghost1", "near", "ghost2")
        assert result is False

    # ── Find All ──────────────────────────────────────────────────

    def test_find_all(self):
        self.service.remember(SpatialObject(name="a"))
        self.service.remember(SpatialObject(name="b"))
        all_objs = self.service.find_all()
        assert len(all_objs) >= 2

    def test_find_all_with_tag(self):
        self.service.remember(SpatialObject(name="x", tags=["test"]))
        found = self.service.find_all(tag="test")
        assert all("test" in o.tags for o in found)

    # ── History ───────────────────────────────────────────────────

    def test_recall_history(self):
        obj = SpatialObject(name="tracked")
        record = self.service.remember(obj)
        history = self.service.recall_history(obj.id)
        assert len(history) >= 1
        assert history[0].object.name == "tracked"

    # ── Count ─────────────────────────────────────────────────────

    def test_object_count(self):
        initial = self.service.object_count()
        self.service.remember(SpatialObject(name="count_me"))
        assert self.service.object_count() == initial + 1
