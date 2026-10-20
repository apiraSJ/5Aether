"""Tests for Step 0.5: Real Panels — MemoryPanel, VisionPanel, SystemPanel."""

import time

from aether.ui.panel.memory_panel import MemoryPanel, MemoryItem
from aether.ui.panel.vision_panel import VisionPanel, VisionSnapshot
from aether.ui.panel.system_panel import SystemPanel, SystemSnapshot
from aether.ui.panel.i_panel import IPanel
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_info import PanelInfo, PanelCapability


# ── MemoryPanel tests ───────────────────────────────────────────────

def test_memory_panel_is_ipanel():
    panel = MemoryPanel()
    assert isinstance(panel, IPanel)


def test_memory_panel_defaults():
    panel = MemoryPanel()
    assert panel.panel_id() == "memory"
    assert panel.get_z_index() == 20
    assert panel.item_count() == 0
    assert panel.get_items() == []


def test_memory_panel_add_item():
    panel = MemoryPanel()
    item = MemoryItem(id="obj1", name="laptop", confidence=0.9)
    panel.add_item(item)
    assert panel.item_count() == 1
    assert panel.get_items()[0].name == "laptop"


def test_memory_panel_add_update():
    """Adding item with same id updates existing."""
    panel = MemoryPanel()
    panel.add_item(MemoryItem(id="obj1", name="laptop"))
    panel.add_item(MemoryItem(id="obj1", name="laptop_v2"))
    assert panel.item_count() == 1
    assert panel.get_items()[0].name == "laptop_v2"


def test_memory_panel_remove():
    panel = MemoryPanel()
    panel.add_item(MemoryItem(id="obj1", name="phone"))
    assert panel.remove_item("obj1") is True
    assert panel.item_count() == 0
    assert panel.remove_item("nonexistent") is False


def test_memory_panel_set_items():
    panel = MemoryPanel()
    items = [
        MemoryItem(id="a", name="alpha"),
        MemoryItem(id="b", name="beta"),
    ]
    panel.set_items(items)
    assert panel.item_count() == 2


def test_memory_panel_filter():
    panel = MemoryPanel()
    panel.add_item(MemoryItem(id="a", name="laptop"))
    panel.add_item(MemoryItem(id="b", name="phone"))
    panel.add_item(MemoryItem(id="c", name="charger"))
    panel.set_filter("lap")
    items = panel.get_items()
    assert len(items) == 1
    assert items[0].name == "laptop"


def test_memory_panel_sort_name():
    panel = MemoryPanel()
    panel.add_item(MemoryItem(id="c", name="charlie"))
    panel.add_item(MemoryItem(id="a", name="alpha"))
    panel.add_item(MemoryItem(id="b", name="bravo"))
    panel.set_sort("name")
    items = panel.get_items()
    assert [i.name for i in items] == ["alpha", "bravo", "charlie"]


def test_memory_panel_sort_confidence():
    panel = MemoryPanel()
    panel.add_item(MemoryItem(id="a", name="low", confidence=0.3))
    panel.add_item(MemoryItem(id="b", name="high", confidence=0.95))
    panel.add_item(MemoryItem(id="c", name="mid", confidence=0.6))
    panel.set_sort("confidence")
    items = panel.get_items()
    assert items[0].name == "high"
    assert items[-1].name == "low"


def test_memory_panel_item_to_dict():
    item = MemoryItem(
        id="obj1", name="test", description="a test object",
        position={"x": 10, "y": 20}, tags=["tag1"],
        confidence=0.8, source="gesture"
    )
    d = item.to_dict()
    assert d["id"] == "obj1"
    assert d["position"] == {"x": 10, "y": 20}
    assert d["tags"] == ["tag1"]


# ── VisionPanel tests ───────────────────────────────────────────────

def test_vision_panel_is_ipanel():
    panel = VisionPanel()
    assert isinstance(panel, IPanel)


def test_vision_panel_defaults():
    panel = VisionPanel()
    assert panel.panel_id() == "vision"
    assert panel.get_z_index() == 10
    assert panel.get_fps() == 0.0
    assert panel.get_object_count() == 0
    assert panel.is_camera_active() is False


def test_vision_panel_update_snapshot():
    panel = VisionPanel()
    snap = VisionSnapshot(
        fps=30.0, camera_active=True, object_count=5,
        hand_count=2, tracking=True,
    )
    panel.update_snapshot(snap)
    assert panel.get_fps() == 30.0
    assert panel.is_camera_active() is True
    assert panel.get_object_count() == 5
    assert panel.get_hand_count() == 2
    assert panel.is_tracking() is True


def test_vision_panel_snapshot_property():
    panel = VisionPanel()
    snap = VisionSnapshot(fps=15.0)
    panel.update_snapshot(snap)
    assert panel.snapshot.fps == 15.0


# ── SystemPanel tests ───────────────────────────────────────────────

def test_system_panel_is_ipanel():
    panel = SystemPanel()
    assert isinstance(panel, IPanel)


def test_system_panel_defaults():
    panel = SystemPanel()
    assert panel.panel_id() == "system"
    assert panel.get_z_index() == 5
    assert panel.snapshot.platform  # should have a value


def test_system_panel_update_uptime():
    panel = SystemPanel()
    panel.update()  # update uptime
    assert panel.get_uptime() >= 0


def test_system_panel_update_snapshot():
    panel = SystemPanel()
    snap = SystemSnapshot(
        uptime=100.0, commands_registered=10,
        commands_processed=50, event_queue_depth=0,
    )
    panel.update_snapshot(snap)
    assert panel.get_commands_processed() == 50
    assert panel.get_event_queue_depth() == 0


def test_system_panel_errors():
    panel = SystemPanel()
    panel.add_error("test error 1")
    panel.add_error("test error 2")
    assert len(panel.snapshot.errors) == 2
    panel.clear_errors()
    assert len(panel.snapshot.errors) == 0


def test_system_panel_errors_max():
    panel = SystemPanel()
    for i in range(15):
        panel.add_error(f"error {i}")
    assert len(panel.snapshot.errors) == 10  # max 10


def test_system_snapshot_to_dict():
    snap = SystemSnapshot(uptime=42.0, platform="Windows")
    d = snap.to_dict()
    assert d["uptime"] == 42.0
    assert d["platform"] == "Windows"


# ── Integration with PanelRegistry ──────────────────────────────────

def test_register_real_panels():
    reg = PanelRegistry()
    mem = MemoryPanel()
    vis = VisionPanel()
    sys_panel = SystemPanel()
    reg.register(PanelInfo(id="memory", type="memory", widget=mem, z_index=20))
    reg.register(PanelInfo(id="vision", type="vision", widget=vis, z_index=10))
    reg.register(PanelInfo(id="system", type="system", widget=sys_panel, z_index=5))
    assert reg.panel_count() == 3
    sorted_panels = reg.get_sorted_by_z()
    assert [p.id for p in sorted_panels] == ["system", "vision", "memory"]


def test_memory_panel_in_registry():
    reg = PanelRegistry()
    mem = MemoryPanel()
    reg.register(PanelInfo(id="memory", type="memory", widget=mem))
    # Add item via panel, verify accessible through registry
    widget = reg.get_widget("memory")
    widget.add_item(MemoryItem(id="obj1", name="laptop"))
    assert widget.item_count() == 1
