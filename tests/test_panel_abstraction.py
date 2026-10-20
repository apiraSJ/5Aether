"""Tests for Step 0.1: Panel Abstraction — IPanel, AbstractPanel, PanelRegistry."""

from aether.ui.panel.i_panel import IPanel
from aether.ui.panel.abstract_panel import AbstractPanel
from aether.ui.panel.panel_info import PanelInfo, PanelCapability
from aether.ui.panel.panel_registry import PanelRegistry


# ── Concrete test panel ─────────────────────────────────────────────

class StubPanel(AbstractPanel):
    """Minimal concrete panel for testing."""

    def __init__(self, panel_id: str = "test", **kwargs):
        super().__init__(panel_id, **kwargs)
        self._update_called = 0
        self._paint_called = 0
        self._theme_applied = None

    def update(self) -> None:
        self._update_called += 1

    def paint(self) -> None:
        self._paint_called += 1

    def set_theme(self, theme: dict) -> None:
        super().set_theme(theme)
        self._theme_applied = theme


# ── IPanel interface tests ──────────────────────────────────────────

def test_ipanel_is_abstract():
    """IPanel cannot be instantiated directly."""
    try:
        IPanel()
        assert False, "Should have raised TypeError"
    except TypeError:
        pass


def test_concrete_panel_implements_ipanel():
    panel = StubPanel()
    assert isinstance(panel, IPanel)


# ── AbstractPanel tests ─────────────────────────────────────────────

def test_abstract_panel_defaults():
    panel = StubPanel("mem")
    assert panel.panel_id() == "mem"
    assert panel.is_visible() is False
    assert panel.geometry() == (0, 0, 400, 300)
    assert panel.get_z_index() == 0
    assert panel.has_focus() is False


def test_abstract_panel_show_hide():
    panel = StubPanel()
    panel.show()
    assert panel.is_visible() is True
    panel.hide()
    assert panel.is_visible() is False
    assert panel.has_focus() is False


def test_abstract_panel_move_resize():
    panel = StubPanel()
    panel.move(100, 200)
    assert panel.geometry() == (100, 200, 400, 300)

    panel.resize(800, 600)
    assert panel.geometry() == (100, 200, 800, 600)

    panel.set_geometry(10, 20, 300, 250)
    assert panel.geometry() == (10, 20, 300, 250)


def test_abstract_panel_z_index():
    panel = StubPanel()
    assert panel.get_z_index() == 0
    panel.set_z_index(50)
    assert panel.get_z_index() == 50


def test_abstract_panel_focus():
    panel = StubPanel()
    assert panel.has_focus() is False
    panel.focus()
    assert panel.has_focus() is True


def test_abstract_panel_theme():
    panel = StubPanel()
    theme = {"colors": {"background": "#000"}}
    panel.set_theme(theme)
    assert panel._theme == theme


def test_abstract_panel_update_paint():
    panel = StubPanel()
    panel.update()
    panel.paint()
    assert panel._update_called == 1
    assert panel._paint_called == 1


# ── PanelInfo tests ─────────────────────────────────────────────────

def test_panel_info_defaults():
    info = PanelInfo(id="test", type="system")
    assert info.id == "test"
    assert info.type == "system"
    assert info.visible is False
    assert info.z_index == 0
    assert PanelCapability.MOVE in info.capabilities
    assert PanelCapability.RESIZE in info.capabilities


def test_panel_info_has_capability():
    info = PanelInfo(id="x", type="x", capabilities=[PanelCapability.MOVE])
    assert info.has_capability(PanelCapability.MOVE)
    assert not info.has_capability(PanelCapability.RESIZE)


def test_panel_info_to_dict():
    info = PanelInfo(id="mem", type="memory", label="Memory")
    d = info.to_dict()
    assert d["id"] == "mem"
    assert d["type"] == "memory"
    assert d["label"] == "Memory"
    assert "widget" not in d  # widget is excluded from serialization


# ── PanelRegistry tests ─────────────────────────────────────────────

def test_registry_register_and_get():
    reg = PanelRegistry()
    info = PanelInfo(id="memory", type="memory", label="Memory")
    reg.register(info)
    assert reg.panel_count() == 1
    fetched = reg.get("memory")
    assert fetched is not None
    assert fetched.id == "memory"


def test_registry_unregister():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="a", type="x"))
    assert reg.unregister("a") is True
    assert reg.get("a") is None
    assert reg.unregister("a") is False


def test_registry_list_all():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="a", type="x"))
    reg.register(PanelInfo(id="b", type="y"))
    all_panels = reg.list_all()
    assert len(all_panels) == 2


def test_registry_list_by_type():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="mem", type="memory"))
    reg.register(PanelInfo(id="vis", type="vision"))
    reg.register(PanelInfo(id="sys", type="system"))
    memory_panels = reg.list_by_type("memory")
    assert len(memory_panels) == 1
    assert memory_panels[0].id == "mem"


def test_registry_show_hide():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="p1", type="x"))
    assert reg.show_panel("p1") is True
    assert reg.get("p1").visible is True
    assert reg.hide_panel("p1") is True
    assert reg.get("p1").visible is False
    assert reg.hide_panel("nonexistent") is False


def test_registry_toggle():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="p1", type="x"))
    assert reg.toggle_panel("p1") is True  # now visible
    assert reg.get("p1").visible is True
    assert reg.toggle_panel("p1") is False  # now hidden
    assert reg.get("p1").visible is False


def test_registry_move():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="p1", type="x"))
    assert reg.move_panel("p1", 100, 200) is True
    info = reg.get("p1")
    assert info.x == 100
    assert info.y == 200
    assert reg.move_panel("nonexistent", 0, 0) is False


def test_registry_resize():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="p1", type="x"))
    assert reg.resize_panel("p1", 800, 600) is True
    info = reg.get("p1")
    assert info.w == 800
    assert info.h == 600


def test_registry_z_index():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="a", type="x", z_index=10))
    reg.register(PanelInfo(id="b", type="x", z_index=5))
    reg.register(PanelInfo(id="c", type="x", z_index=20))
    sorted_panels = reg.get_sorted_by_z()
    assert [p.id for p in sorted_panels] == ["b", "a", "c"]


def test_registry_focus():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="a", type="x"))
    reg.register(PanelInfo(id="b", type="x"))
    reg.focus_panel("a")
    assert reg.get_focused().id == "a"
    reg.focus_panel("b")
    assert reg.get_focused().id == "b"
    assert reg.get("a").has_focus is False


def test_registry_list_visible():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="a", type="x"))
    reg.register(PanelInfo(id="b", type="x"))
    reg.show_panel("a")
    visible = reg.list_visible()
    assert len(visible) == 1
    assert visible[0].id == "a"


def test_registry_list_with_capability():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="a", type="x", capabilities=[PanelCapability.MOVE]))
    reg.register(PanelInfo(id="b", type="x", capabilities=[]))
    movable = reg.list_with_capability(PanelCapability.MOVE)
    assert len(movable) == 1
    assert movable[0].id == "a"


def test_registry_apply_theme():
    reg = PanelRegistry()
    panel = StubPanel("p1")
    info = PanelInfo(id="p1", type="x", widget=panel)
    reg.register(info)
    count = reg.apply_theme({"colors": {"primary": "#0f0"}})
    assert count == 1
    assert panel._theme_applied == {"colors": {"primary": "#0f0"}}


def test_registry_to_dict():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="a", type="x"))
    reg.register(PanelInfo(id="b", type="y"))
    d = reg.to_dict()
    assert d["panel_count"] == 2
    assert len(d["panels"]) == 2


def test_registry_widget_get():
    panel = StubPanel("w1")
    reg = PanelRegistry()
    reg.register(PanelInfo(id="w1", type="x", widget=panel))
    assert reg.get_widget("w1") is panel
    assert reg.get_widget("nonexistent") is None


def test_registry_change_listener():
    reg = PanelRegistry()
    events = []
    reg.set_change_listener(lambda pid, action: events.append((pid, action)))
    reg.register(PanelInfo(id="a", type="x"))
    reg.show_panel("a")
    reg.hide_panel("a")
    assert len(events) == 3
    assert events[0] == ("a", "registered")
    assert events[1] == ("a", "shown")
    assert events[2] == ("a", "hidden")


def test_registry_geometry():
    reg = PanelRegistry()
    reg.register(PanelInfo(id="p1", type="x"))
    assert reg.set_geometry("p1", 10, 20, 300, 250) is True
    info = reg.get("p1")
    assert (info.x, info.y, info.w, info.h) == (10, 20, 300, 250)
    assert reg.set_geometry("nonexistent", 0, 0, 0, 0) is False


def test_registry_overwrite():
    """Registering same id overwrites previous."""
    reg = PanelRegistry()
    reg.register(PanelInfo(id="a", type="x", label="v1"))
    reg.register(PanelInfo(id="a", type="y", label="v2"))
    assert reg.panel_count() == 1
    assert reg.get("a").label == "v2"
