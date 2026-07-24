"""Contract tests for ISpatialRepository.

Every adapter that implements ISpatialRepository must pass these tests.
These tests do NOT test implementation details — they test the contract.

Run with: pytest tests/contracts/test_spatial_repository.py -v
"""

import pytest
from datetime import datetime
from typing import Optional

from aether.domain.spatial_object import SpatialObject, SpatialRelation
from aether.core.interfaces.i_memory_repository import ISpatialRepository


class SpatialRepositoryContract:
    """Mixin class for spatial repository contract tests.

    Subclasses must set self.repo in setup_method().
    """

    repo: ISpatialRepository

    def setup_method(self):
        """Override in subclass to initialize self.repo."""
        raise NotImplementedError

    # ── Save / Find ───────────────────────────────────────────────

    def test_save_and_find_by_id(self):
        obj = SpatialObject(name="laptop", position={"room": "desk"})
        assert self.repo.save(obj) is True
        found = self.repo.find_by_id(obj.id)
        assert found is not None
        assert found.name == "laptop"
        assert found.position["room"] == "desk"

    def test_find_by_name(self):
        obj = SpatialObject(name="charger", position={"room": "desk"})
        self.repo.save(obj)
        found = self.repo.find_by_name("charger")
        assert found is not None
        assert found.name == "charger"

    def test_find_by_name_not_found(self):
        found = self.repo.find_by_name("nonexistent")
        assert found is None

    def test_save_updates_existing(self):
        obj = SpatialObject(name="monitor", position={"room": "desk"})
        self.repo.save(obj)
        updated = obj.with_update(position={"room": "lab"})
        self.repo.save(updated)
        found = self.repo.find_by_id(obj.id)
        assert found.position["room"] == "lab"

    # ── Find All / Filter ─────────────────────────────────────────

    def test_find_all(self):
        self.repo.save(SpatialObject(name="obj1", tags=["a"]))
        self.repo.save(SpatialObject(name="obj2", tags=["b"]))
        all_objs = self.repo.find_all()
        assert len(all_objs) >= 2

    def test_find_all_with_tag(self):
        self.repo.save(SpatialObject(name="laptop", tags=["electronics"]))
        self.repo.save(SpatialObject(name="book", tags=["stationery"]))
        electronics = self.repo.find_all(tag="electronics")
        assert all("electronics" in o.tags for o in electronics)

    # ── Relations ─────────────────────────────────────────────────

    def test_find_near(self):
        desk = SpatialObject(name="desk", position={"x": 0, "y": 0, "z": 0})
        laptop = SpatialObject(name="laptop", position={"x": 0.1, "y": 0, "z": 0})
        self.repo.save(desk)
        self.repo.save(laptop)
        near = self.repo.find_near("desk", radius=1.0)
        names = [o.name for o in near]
        assert "laptop" in names

    def test_find_by_relation(self):
        laptop = SpatialObject(name="laptop")
        charger = SpatialObject(
            name="charger",
            relations=[SpatialRelation(type="left_of", target_id=laptop.id)],
        )
        self.repo.save(laptop)
        self.repo.save(charger)
        found = self.repo.find_by_relation("left_of", laptop.id)
        assert any(o.name == "charger" for o in found)

    # ── Delete ────────────────────────────────────────────────────

    def test_delete(self):
        obj = SpatialObject(name="temp")
        self.repo.save(obj)
        assert self.repo.delete(obj.id) is True
        assert self.repo.find_by_id(obj.id) is None

    def test_delete_nonexistent(self):
        assert self.repo.delete("nonexistent_id") is False

    # ── Count ─────────────────────────────────────────────────────

    def test_count(self):
        initial = self.repo.count()
        self.repo.save(SpatialObject(name="count_test"))
        assert self.repo.count() == initial + 1
