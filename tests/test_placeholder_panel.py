"""Tests for PlaceholderPanel — "Coming Soon" panel for workspaces."""

from aether.panels.placeholder_panel import PlaceholderPanel
from aether.ui.panel.panel_info import PanelCapability


def test_placeholder_initialization():
    panel = PlaceholderPanel("test_panel", "Test Label", 100, 200, 400, 300, 5)
    assert panel.panel_id() == "test_panel"
    assert panel.label == "Test Label"
    assert panel.geometry() == (100, 200, 400, 300)


def test_placeholder_default_geometry():
    panel = PlaceholderPanel("default")
    assert panel.geometry() == (0, 0, 400, 300)


def test_placeholder_show_hide():
    panel = PlaceholderPanel("test_panel")
    assert not panel.is_visible()
    panel.show()
    assert panel.is_visible()
    panel.hide()
    assert not panel.is_visible()


def test_placeholder_move():
    panel = PlaceholderPanel("test_panel", x=0, y=0)
    panel.move(150, 250)
    assert panel.geometry() == (150, 250, 400, 300)


def test_placeholder_resize():
    panel = PlaceholderPanel("test_panel")
    panel.resize(600, 400)
    assert panel.geometry() == (0, 0, 600, 400)


def test_placeholder_focus():
    panel = PlaceholderPanel("test_panel")
    assert not panel.has_focus()
    panel.focus()
    assert panel.has_focus()


def test_placeholder_z_index():
    panel = PlaceholderPanel("test_panel", z_index=10)
    assert panel.get_z_index() == 10
    panel.set_z_index(20)
    assert panel.get_z_index() == 20


def test_placeholder_capabilities():
    panel = PlaceholderPanel("test_panel")
    assert panel.has_capability(PanelCapability.MOVE)
    assert panel.has_capability(PanelCapability.RESIZE)
    assert panel.has_capability(PanelCapability.HIDE)
    assert panel.has_capability(PanelCapability.FOCUS)


def test_placeholder_update_and_paint():
    """update() and paint() should be callable without side effects."""
    panel = PlaceholderPanel("test_panel")
    panel.update()
    panel.paint()


def test_placeholder_theme():
    panel = PlaceholderPanel("test_panel")
    theme = {"colors": {"background": "#000"}}
    panel.set_theme(theme)
