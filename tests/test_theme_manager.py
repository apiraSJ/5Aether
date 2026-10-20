"""Tests for Step 0.3: Theme System — ThemeManager, dark/cyber themes."""

import json
from pathlib import Path

from aether.ui.panel.theme_manager import ThemeManager, DEFAULT_THEME
from aether.ui.panel.panel_info import PanelInfo
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.abstract_panel import AbstractPanel


# ── Fixtures ────────────────────────────────────────────────────────

class StubPanel(AbstractPanel):
    def __init__(self, pid="test"):
        super().__init__(pid)
        self._last_theme = None

    def set_theme(self, theme):
        self._last_theme = theme


# ── List tests ──────────────────────────────────────────────────────

def test_list_themes_includes_default(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    themes = mgr.list_themes()
    assert "default" in themes


def test_list_themes_discovers_files(tmp_path):
    (tmp_path / "dark.json").write_text('{"name":"dark","colors":{}}')
    (tmp_path / "cyber.json").write_text('{"name":"cyber","colors":{}}')
    mgr = ThemeManager(themes_dir=tmp_path)
    themes = mgr.list_themes()
    assert "dark" in themes
    assert "cyber" in themes
    assert "default" in themes


# ── Load tests ──────────────────────────────────────────────────────

def test_load_default(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.load_theme("default") is True
    assert mgr.current_name == "default"
    assert mgr.get_theme()["name"] == "default"


def test_load_from_file(tmp_path):
    theme_data = {
        "name": "test_theme",
        "colors": {"primary": "#ff0000"},
        "opacity": {"panel": 0.5},
    }
    (tmp_path / "test_theme.json").write_text(json.dumps(theme_data))
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.load_theme("test_theme") is True
    assert mgr.get_color("colors.primary") == "#ff0000"
    assert mgr.get_opacity("panel") == 0.5


def test_load_nonexistent(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.load_theme("nonexistent") is False


def test_load_merges_with_default(tmp_path):
    """Loading a partial theme should fill missing keys from DEFAULT_THEME."""
    partial = {"name": "partial", "colors": {"primary": "#00ff00"}}
    (tmp_path / "partial.json").write_text(json.dumps(partial))
    mgr = ThemeManager(themes_dir=tmp_path)
    mgr.load_theme("partial")
    # primary should be overridden
    assert mgr.get_color("colors.primary") == "#00ff00"
    # background should come from default
    assert mgr.get_color("colors.background") == DEFAULT_THEME["colors"]["background"]


def test_load_invalid_json(tmp_path):
    (tmp_path / "bad.json").write_text("not json{{{")
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.load_theme("bad") is False


# ── Get tests ───────────────────────────────────────────────────────

def test_get_color(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.get_color("colors.primary") == DEFAULT_THEME["colors"]["primary"]


def test_get_color_dot_notation(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.get_color("colors.nonexistent", "#000") == "#000"


def test_get_opacity(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.get_opacity("panel") == DEFAULT_THEME["opacity"]["panel"]


def test_get_opacity_missing(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.get_opacity("nonexistent", 0.5) == 0.5


def test_get_font_size(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.get_font_size("title_size") == DEFAULT_THEME["typography"]["title_size"]


def test_get_border_radius(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.get_border_radius() == DEFAULT_THEME["shape"]["border_radius"]


def test_get_animation_duration(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.get_animation_duration() == DEFAULT_THEME["animation"]["duration_ms"]


# ── Apply tests ─────────────────────────────────────────────────────

def test_apply_to_registry(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    panel = StubPanel("p1")
    reg = PanelRegistry()
    reg.register(PanelInfo(id="p1", type="x", widget=panel))
    count = mgr.apply_to_registry(reg)
    assert count == 1
    assert panel._last_theme is not None
    assert panel._last_theme["name"] == "default"


def test_apply_to_registry_multiple(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    panels = [StubPanel(f"p{i}") for i in range(3)]
    reg = PanelRegistry()
    for p in panels:
        reg.register(PanelInfo(id=p.panel_id(), type="x", widget=p))
    count = mgr.apply_to_registry(reg)
    assert count == 3


# ── Save tests ──────────────────────────────────────────────────────

def test_save_theme(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    theme = {"colors": {"primary": "#123456"}}
    assert mgr.save_theme("my_theme", theme, description="Custom") is True
    path = tmp_path / "my_theme.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["name"] == "my_theme"
    assert data["description"] == "Custom"
    assert data["colors"]["primary"] == "#123456"


def test_save_and_load_roundtrip(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    theme = {"colors": {"primary": "#aabbcc"}, "opacity": {"panel": 0.7}}
    mgr.save_theme("roundtrip", theme)
    mgr2 = ThemeManager(themes_dir=tmp_path)
    assert mgr2.load_theme("roundtrip") is True
    assert mgr2.get_color("colors.primary") == "#aabbcc"
    assert mgr2.get_opacity("panel") == 0.7


# ── Delete tests ────────────────────────────────────────────────────

def test_delete_theme(tmp_path):
    (tmp_path / "deleteme.json").write_text('{"name":"deleteme"}')
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.delete_theme("deleteme") is True
    assert not (tmp_path / "deleteme.json").exists()


def test_delete_nonexistent(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.delete_theme("nope") is False


def test_delete_default_blocked(tmp_path):
    mgr = ThemeManager(themes_dir=tmp_path)
    assert mgr.delete_theme("default") is False


# ── Built-in theme files ────────────────────────────────────────────

def test_dark_theme_file_exists():
    """Verify dark.json ships with the project."""
    path = Path(__file__).resolve().parent.parent / "data" / "themes" / "dark.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "dark"
    assert "colors" in data
    assert "primary" in data["colors"]


def test_cyberpunk_theme_file_exists():
    """Verify cyberpunk.json ships with the project."""
    path = Path(__file__).resolve().parent.parent / "data" / "themes" / "cyberpunk.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "cyberpunk"
    assert "colors" in data
    assert "primary" in data["colors"]
