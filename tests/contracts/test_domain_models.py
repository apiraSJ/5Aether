"""Contract tests for domain models.

These tests verify that domain models behave correctly as immutable
value objects with snapshot semantics.

Run with: pytest tests/contracts/test_domain_models.py -v
"""

import pytest
from datetime import datetime

from aether.domain.spatial_object import SpatialObject, SpatialRelation
from aether.domain.memory_record import MemoryRecord, RecallResult
from aether.domain.context_snapshot import ContextSnapshot, InteractionMode
from aether.domain.task import Task, TaskStatus


# ── SpatialObject ───────────────────────────────────────────────────

class TestSpatialObject:
    def test_creation(self):
        obj = SpatialObject(name="laptop", position={"room": "desk"})
        assert obj.name == "laptop"
        assert obj.position["room"] == "desk"
        assert obj.id.startswith("obj_")

    def test_frozen(self):
        obj = SpatialObject(name="laptop")
        with pytest.raises(AttributeError):
            obj.name = "charger"

    def test_with_update_returns_new(self):
        obj = SpatialObject(name="laptop", position={"room": "desk"})
        updated = obj.with_update(position={"room": "lab"})
        assert obj.position["room"] == "desk"  # original unchanged
        assert updated.position["room"] == "lab"

    def test_add_relation(self):
        obj = SpatialObject(name="laptop")
        rel = SpatialRelation(type="left_of", target_id="obj_charger")
        updated = obj.add_relation(rel)
        assert len(updated.relations) == 1
        assert len(obj.relations) == 0  # original unchanged

    def test_remove_relation(self):
        rel = SpatialRelation(type="left_of", target_id="obj_charger")
        obj = SpatialObject(name="laptop", relations=[rel])
        updated = obj.remove_relation("obj_charger")
        assert len(updated.relations) == 0

    def test_has_relation(self):
        rel = SpatialRelation(type="left_of", target_id="obj_charger")
        obj = SpatialObject(name="laptop", relations=[rel])
        assert obj.has_relation("left_of", "obj_charger") is True
        assert obj.has_relation("right_of", "obj_charger") is False

    def test_related_objects(self):
        rel1 = SpatialRelation(type="left_of", target_id="a")
        rel2 = SpatialRelation(type="near", target_id="b")
        obj = SpatialObject(name="x", relations=[rel1, rel2])
        assert set(obj.related_objects()) == {"a", "b"}
        assert obj.related_objects("left_of") == ["a"]


# ── SpatialRelation ─────────────────────────────────────────────────

class TestSpatialRelation:
    def test_creation(self):
        rel = SpatialRelation(type="left_of", target_id="obj_charger")
        assert rel.type == "left_of"
        assert rel.target_id == "obj_charger"
        assert rel.confidence == 1.0

    def test_frozen(self):
        rel = SpatialRelation(type="left_of", target_id="x")
        with pytest.raises(AttributeError):
            rel.type = "right_of"


# ── MemoryRecord ────────────────────────────────────────────────────

class TestMemoryRecord:
    def test_creation(self):
        obj = SpatialObject(name="laptop")
        record = MemoryRecord(object=obj, source="gesture")
        assert record.object.name == "laptop"
        assert record.source == "gesture"
        assert record.access_count == 0

    def test_access_increments(self):
        obj = SpatialObject(name="laptop")
        record = MemoryRecord(object=obj)
        accessed = record.access()
        assert accessed.access_count == 1
        assert record.access_count == 0  # original unchanged

    def test_age_days(self):
        obj = SpatialObject(name="laptop")
        record = MemoryRecord(object=obj)
        assert record.age_days >= 0

    def test_is_expired_default(self):
        record = MemoryRecord()
        assert record.is_expired is False


# ── RecallResult ────────────────────────────────────────────────────

class TestRecallResult:
    def test_found(self):
        obj = SpatialObject(name="laptop")
        result = RecallResult(found=True, object=obj, query="laptop")
        assert result.found is True
        assert result.object.name == "laptop"

    def test_not_found(self):
        result = RecallResult(found=False, query="ghost")
        assert result.found is False
        assert result.object is None


# ── ContextSnapshot ─────────────────────────────────────────────────

class TestContextSnapshot:
    def test_creation(self):
        ctx = ContextSnapshot(
            interaction_mode=InteractionMode.DEVELOPER,
            active_window="VS Code",
        )
        assert ctx.interaction_mode == InteractionMode.DEVELOPER
        assert ctx.active_window == "VS Code"

    def test_frozen(self):
        ctx = ContextSnapshot()
        with pytest.raises(AttributeError):
            ctx.interaction_mode = InteractionMode.DEVELOPER

    def test_with_mode(self):
        ctx = ContextSnapshot(interaction_mode=InteractionMode.NORMAL)
        dev_ctx = ctx.with_mode(InteractionMode.DEVELOPER)
        assert ctx.interaction_mode == InteractionMode.NORMAL  # original
        assert dev_ctx.interaction_mode == InteractionMode.DEVELOPER

    def test_is_developer(self):
        ctx = ContextSnapshot(interaction_mode=InteractionMode.DEVELOPER)
        assert ctx.is_developer is True
        normal = ContextSnapshot(interaction_mode=InteractionMode.NORMAL)
        assert normal.is_developer is False

    def test_is_focused(self):
        ctx = ContextSnapshot(focused_object="obj_laptop")
        assert ctx.is_focused is True
        empty = ContextSnapshot()
        assert empty.is_focused is False


# ── Task ────────────────────────────────────────────────────────────

class TestTask:
    def test_creation(self):
        task = Task(name="remember laptop")
        assert task.name == "remember laptop"
        assert task.status == TaskStatus.PENDING

    def test_lifecycle(self):
        task = Task(name="test")
        running = task.start()
        assert running.status == TaskStatus.RUNNING
        completed = running.complete(result="done")
        assert completed.status == TaskStatus.COMPLETED
        assert completed.result == "done"

    def test_cancel(self):
        task = Task(name="test")
        cancelled = task.cancel(reason="user abort")
        assert cancelled.status == TaskStatus.CANCELLED
        assert cancelled.error == "user abort"

    def test_is_active(self):
        pending = Task(name="t", status=TaskStatus.PENDING)
        assert pending.is_active is True
        done = Task(name="t", status=TaskStatus.COMPLETED)
        assert done.is_active is False

    def test_frozen(self):
        task = Task(name="test")
        with pytest.raises(AttributeError):
            task.name = "other"
