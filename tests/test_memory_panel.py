"""Tests for MemoryPanel — view-only panel that dispatches commands and subscribes to events."""

from aether.panels.memory_panel import MemoryPanel, MemoryPanelItem


def test_memory_panel_initialization():
    panel = MemoryPanel(x=10, y=20, width=500, height=400)
    assert panel.panel_id() == "memory"
    assert panel.geometry() == (10, 20, 500, 400)
    assert panel.item_count() == 0


def test_memory_panel_gets_items():
    panel = MemoryPanel()
    items = panel.get_items()
    assert isinstance(items, list)
    assert len(items) == 0


def test_memory_panel_item_count():
    panel = MemoryPanel()
    assert panel.item_count() == 0


def test_memory_panel_select_item_no_bus():
    """Selecting an item without a command bus should not crash."""
    panel = MemoryPanel()
    panel.select_item("test_key")
    assert panel.get_selected_key() == "test_key"


def test_memory_panel_set_detail():
    panel = MemoryPanel()
    assert panel.get_detail() is None
    detail = {"key": "bottle", "type": "spatial", "position": {"x": 0.5, "y": 0.3}}
    panel.set_detail(detail)
    assert panel.get_detail() == detail


def test_memory_panel_clear_detail():
    panel = MemoryPanel()
    panel.set_detail({"key": "test"})
    panel.set_detail(None)
    assert panel.get_detail() is None


def test_memory_panel_update_and_paint():
    """update() and paint() should be callable without side effects."""
    panel = MemoryPanel()
    panel.update()
    panel.paint()


def test_memory_panel_set_search_query_no_bus():
    """Setting search query without a command bus should not crash."""
    panel = MemoryPanel()
    panel.set_search_query("bottle")
    assert panel.get_items() == []


def test_memory_panel_item_dataclass():
    item = MemoryPanelItem(key="bottle", value='{"color": "blue"}', memory_type="spatial")
    assert item.key == "bottle"
    assert item.memory_type == "spatial"
    d = item.to_dict()
    assert d["key"] == "bottle"
    assert d["type"] == "spatial"


def test_memory_panel_item_with_position():
    item = MemoryPanelItem(
        key="cup", value="object", memory_type="spatial",
        confidence=0.95, position={"x": 0.3, "y": 0.7, "z": 0.0},
        label="cup",
    )
    assert item.confidence == 0.95
    assert item.position["x"] == 0.3
    assert item.label == "cup"
