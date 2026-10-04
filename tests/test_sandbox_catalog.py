"""Tests for the simulated maintenance component catalog (M1 sandbox)."""

from __future__ import annotations

import pytest

from aether.sandbox.catalog import (
    COMPONENTS,
    COMPONENT_FIELDS,
    COMPONENT_IDS,
    get_component,
    validate_catalog,
)


class TestCatalogSchema:
    def test_catalog_has_3_to_5_components(self):
        assert 3 <= len(COMPONENTS) <= 5

    def test_catalog_has_no_schema_violations(self):
        assert validate_catalog() == []

    def test_component_ids_are_sequential_1_to_count(self):
        assert COMPONENT_IDS == tuple(str(i) for i in range(1, len(COMPONENTS) + 1))

    def test_every_record_has_all_required_fields_nonempty(self):
        for comp in COMPONENTS:
            for field in COMPONENT_FIELDS:
                assert comp.get(field), f"component {comp.get('id')} missing {field}"

    def test_each_component_is_explicitly_simulated(self):
        for comp in COMPONENTS:
            assert "SIMULATED" in comp["source_manual"].upper()

    def test_every_component_has_unique_id(self):
        ids = [c["id"] for c in COMPONENTS]
        assert len(ids) == len(set(ids))


class TestGetComponent:
    def test_returns_known_component(self):
        comp = get_component("1")
        assert comp is not None
        assert comp["id"] == "1"
        assert comp["name"]

    def test_accepts_integer_argument(self):
        comp = get_component(3)
        assert comp is not None
        assert comp["id"] == "3"

    def test_returns_none_for_unknown_id(self):
        assert get_component("9") is None
        assert get_component("") is None