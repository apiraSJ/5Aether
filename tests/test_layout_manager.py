"""Tests for Step 0.2: Layout System — LayoutManager, JSON save/load."""

import json
import tempfile
from pathlib import Path

from aether.ui.panel.panel_info import PanelInfo
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.layout_manager import LayoutManager


# ── Fixtures ────────────────────────────────────────────────────────

def _make_registry_with_panels():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="memory", type="memory", x=0, y=0, w=400, h=300, visible=False))
    reg.register(PanelInfo(id="vision", type="vision", x=420, y=0, w=400, h=300, visible=True))
    reg.register(PanelInfo(id="system", type="system", x=0, y=320, w=840, h=200, visible=False))
    return reg


def _make_manager(tmp_path):
    reg = _make_registry_with_panels()
    mgr = LayoutManager(reg, layouts_dir=tmp_path)
    return mgr, reg, tmp_path


# ── Save tests ──────────────────────────────────────────────────────

def test_save_creates_file(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    layout = mgr.save("test_layout")
    assert layout["name"] == "test_layout"
    assert len(layout["panels"]) == 3
    assert (tmp_path / "test_layout.json").exists()


def test_save_includes_panel_geometry(tmp_path):
    mgr, reg, _ = _make_manager(tmp_path)
    reg.move_panel("memory", 100, 200)
    layout = mgr.save("g")
    mem_panel = next(p for p in layout["panels"] if p["id"] == "memory")
    assert mem_panel["x"] == 100
    assert mem_panel["y"] == 200


def test_save_sets_current_layout(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    assert mgr.current_layout is None
    mgr.save("my_layout")
    assert mgr.current_layout == "my_layout"


# ── Load tests ──────────────────────────────────────────────────────

def test_load_applies_geometry(tmp_path):
    mgr, reg, _ = _make_manager(tmp_path)
    mgr.save("layout1")
    # Move panels to different positions
    reg.move_panel("memory", 500, 500)
    reg.move_panel("vision", 500, 500)
    # Load should restore original positions
    assert mgr.load("layout1") is True
    mem = reg.get("memory")
    assert mem.x == 0
    assert mem.y == 0


def test_load_shows_hides_panels(tmp_path):
    mgr, reg, _ = _make_manager(tmp_path)
    # Save with memory visible
    reg.show_panel("memory")
    mgr.save("vis_layout")
    reg.hide_panel("memory")
    # Load should show memory again
    mgr.load("vis_layout")
    assert reg.get("memory").visible is True


def test_load_nonexistent_returns_false(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    assert mgr.load("nonexistent") is False


def test_load_sets_current_layout(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    mgr.save("a")
    mgr.save("b")
    mgr.load("a")
    assert mgr.current_layout == "a"


# ── List tests ──────────────────────────────────────────────────────

def test_list_layouts(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    mgr.save("alpha")
    mgr.save("beta")
    mgr.save("gamma")
    layouts = mgr.list_layouts()
    assert layouts == ["alpha", "beta", "gamma"]


def test_list_empty(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    assert mgr.list_layouts() == []


# ── Delete tests ────────────────────────────────────────────────────

def test_delete(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    mgr.save("to_delete")
    assert mgr.delete("to_delete") is True
    assert not (tmp_path / "to_delete.json").exists()
    assert mgr.delete("to_delete") is False  # already deleted


def test_delete_clears_current_if_active(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    mgr.save("active")
    assert mgr.current_layout == "active"
    mgr.delete("active")
    assert mgr.current_layout is None


# ── Reset tests ─────────────────────────────────────────────────────

def test_reset(tmp_path):
    mgr, reg, _ = _make_manager(tmp_path)
    reg.move_panel("memory", 100, 100)
    reg.show_panel("memory")
    mgr.save("before_reset")
    mgr.reset()
    assert mgr.current_layout is None
    mem = reg.get("memory")
    assert mem.visible is False


# ── Default layout tests ────────────────────────────────────────────

def test_save_default(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    layout = mgr.save_default()
    assert layout["name"] == "default"
    assert (tmp_path / "default.json").exists()


def test_load_default(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    mgr.save_default()
    assert mgr.load_default() is True
    assert mgr.current_layout == "default"


# ── get_layout_info tests ───────────────────────────────────────────

def test_get_layout_info(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    mgr.save("info_test", description="test layout")
    info = mgr.get_layout_info("info_test")
    assert info is not None
    assert info["name"] == "info_test"
    assert info["description"] == "test layout"


def test_get_layout_info_nonexistent(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    assert mgr.get_layout_info("nope") is None


# ── Layout file content ─────────────────────────────────────────────

def test_layout_json_is_valid(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    mgr.save("valid_json")
    content = (tmp_path / "valid_json.json").read_text(encoding="utf-8")
    data = json.loads(content)
    assert data["name"] == "valid_json"
    assert "panels" in data
    assert "created_at" in data


# ── Path safety ─────────────────────────────────────────────────────

def test_path_traversal_blocked(tmp_path):
    mgr, _, _ = _make_manager(tmp_path)
    mgr.save("../../../etc/passwd")
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert ".." not in files[0].name


# ── Panel not in registry ───────────────────────────────────────────

def test_load_skips_unknown_panel(tmp_path):
    mgr, reg, _ = _make_manager(tmp_path)
    # Manually write a layout referencing unknown panel
    layout = {
        "name": "with_unknown",
        "panels": [
            {"id": "memory", "x": 10, "y": 20, "w": 300, "h": 250, "visible": True},
            {"id": "ghost_panel", "x": 0, "y": 0, "w": 100, "h": 100, "visible": True},
        ],
    }
    (tmp_path / "with_unknown.json").write_text(json.dumps(layout), encoding="utf-8")
    assert mgr.load("with_unknown") is True
    mem = reg.get("memory")
    assert mem.x == 10
    # ghost_panel should be skipped, no error
