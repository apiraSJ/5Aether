"""Tests for Step 0.6: Panel/Layout/Theme commands in SystemCommandPlugin."""

import json
import tempfile
from pathlib import Path

from aether.core.event_bus_v2 import EventBus
from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.result_pipeline import ResultPipeline
from aether.core.command_registry import CommandRegistry
from aether.core.service_container import ServiceContainer
from aether.plugins.system_commands_plugin import SystemCommandPlugin
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_info import PanelInfo
from aether.ui.panel.layout_manager import LayoutManager
from aether.ui.panel.theme_manager import ThemeManager
from aether.ui.panel.memory_panel import MemoryPanel


# ── Fixtures ────────────────────────────────────────────────────────

def _make_container(tmp_path=None):
    c = ServiceContainer()
    bus = EventBus(queued=True)
    pipeline = ResultPipeline()
    cmd_bus = CommandBus(result_pipeline=pipeline, event_bus=bus)
    c.register_instance("event_bus", bus)
    c.register_instance("command_bus", cmd_bus)
    c.register_instance("result_pipeline", pipeline)
    c.register_instance("config", {})

    # Register UI services
    reg = PanelRegistry()
    reg.register(PanelInfo(id="memory", type="memory", widget=MemoryPanel(), z_index=20))
    reg.register(PanelInfo(id="vision", type="vision", z_index=10))
    c.register_instance("panel_registry", reg)

    layouts_dir = tmp_path or Path(tempfile.mkdtemp())
    mgr = LayoutManager(reg, layouts_dir=layouts_dir)
    c.register_instance("layout_manager", mgr)

    theme_mgr = ThemeManager(themes_dir=layouts_dir)
    c.register_instance("theme_manager", theme_mgr)

    return c, bus, cmd_bus, reg, mgr, theme_mgr


def _init_plugin(c):
    plugin = SystemCommandPlugin()
    plugin.initialize(c)
    return plugin


# ── Panel show/hide/toggle ──────────────────────────────────────────

def test_panel_show(tmp_path):
    c, _, cmd_bus, reg, _, _ = _make_container(tmp_path)
    _init_plugin(c)
    result = cmd_bus.dispatch_sync(Command(
        name="system.panel.show", source="test",
        params={"panel_id": "memory"},
    ))
    assert result.get("message") == "Panel 'memory' shown"
    assert reg.get("memory").visible is True


def test_panel_hide(tmp_path):
    c, _, cmd_bus, reg, _, _ = _make_container(tmp_path)
    _init_plugin(c)
    reg.show_panel("memory")
    result = cmd_bus.dispatch_sync(Command(
        name="system.panel.hide", source="test",
        params={"panel_id": "memory"},
    ))
    assert result.get("message") == "Panel 'memory' hidden"
    assert reg.get("memory").visible is False


def test_panel_toggle(tmp_path):
    c, _, cmd_bus, reg, _, _ = _make_container(tmp_path)
    _init_plugin(c)
    result = cmd_bus.dispatch_sync(Command(
        name="system.panel.toggle", source="test",
        params={"panel_id": "memory"},
    ))
    assert "shown" in result.get("message", "")
    assert reg.get("memory").visible is True


def test_panel_not_found(tmp_path):
    c, _, cmd_bus, _, _, _ = _make_container(tmp_path)
    _init_plugin(c)
    result = cmd_bus.dispatch_sync(Command(
        name="system.panel.show", source="test",
        params={"panel_id": "nonexistent"},
    ))
    assert "not found" in result.get("message", "")


def test_panel_no_id(tmp_path):
    c, _, cmd_bus, _, _, _ = _make_container(tmp_path)
    _init_plugin(c)
    result = cmd_bus.dispatch_sync(Command(
        name="system.panel.show", source="test", params={},
    ))
    assert "Usage" in result.get("message", "")


def test_panel_list(tmp_path):
    c, _, cmd_bus, _, _, _ = _make_container(tmp_path)
    _init_plugin(c)
    result = cmd_bus.dispatch_sync(Command(
        name="system.panel.list", source="test", params={},
    ))
    assert "2 panels" in result.get("message", "")
    assert "memory" in result.get("message", "")


# ── Layout commands ─────────────────────────────────────────────────

def test_layout_save(tmp_path):
    c, _, cmd_bus, _, mgr, _ = _make_container(tmp_path)
    _init_plugin(c)
    result = cmd_bus.dispatch_sync(Command(
        name="system.layout.save", source="test",
        params={"name": "dev"},
    ))
    assert "saved" in result.get("message", "")
    assert mgr.current_layout == "dev"


def test_layout_load(tmp_path):
    c, _, cmd_bus, _, mgr, _ = _make_container(tmp_path)
    _init_plugin(c)
    mgr.save("dev")
    result = cmd_bus.dispatch_sync(Command(
        name="system.layout.load", source="test",
        params={"name": "dev"},
    ))
    assert "loaded" in result.get("message", "")


def test_layout_list(tmp_path):
    c, _, cmd_bus, _, mgr, _ = _make_container(tmp_path)
    _init_plugin(c)
    mgr.save("a")
    mgr.save("b")
    result = cmd_bus.dispatch_sync(Command(
        name="system.layout.list", source="test", params={},
    ))
    assert "2 layouts" in result.get("message", "")


def test_layout_delete(tmp_path):
    c, _, cmd_bus, _, mgr, _ = _make_container(tmp_path)
    _init_plugin(c)
    mgr.save("todelete")
    result = cmd_bus.dispatch_sync(Command(
        name="system.layout.delete", source="test",
        params={"name": "todelete"},
    ))
    assert "deleted" in result.get("message", "")
    assert "todelete" not in mgr.list_layouts()


def test_layout_reset(tmp_path):
    c, _, cmd_bus, reg, mgr, _ = _make_container(tmp_path)
    _init_plugin(c)
    reg.show_panel("memory")
    mgr.save("before")
    result = cmd_bus.dispatch_sync(Command(
        name="system.layout.reset", source="test", params={},
    ))
    assert "reset" in result.get("message", "").lower()
    assert mgr.current_layout is None


def test_layout_not_found(tmp_path):
    c, _, cmd_bus, _, _, _ = _make_container(tmp_path)
    _init_plugin(c)
    result = cmd_bus.dispatch_sync(Command(
        name="system.layout.load", source="test",
        params={"name": "nonexistent"},
    ))
    assert "not found" in result.get("message", "")


# ── Theme commands ──────────────────────────────────────────────────

def test_theme_list(tmp_path):
    c, _, cmd_bus, _, _, theme_mgr = _make_container(tmp_path)
    _init_plugin(c)
    theme_mgr.save_theme("custom", {"colors": {"primary": "#fff"}})
    result = cmd_bus.dispatch_sync(Command(
        name="system.theme.list", source="test", params={},
    ))
    message = result.get("message", "")
    assert "themes" in message


def test_theme_apply(tmp_path):
    c, _, cmd_bus, _, _, theme_mgr = _make_container(tmp_path)
    _init_plugin(c)
    theme_mgr.save_theme("cyber", {"colors": {"primary": "#0ff"}})
    result = cmd_bus.dispatch_sync(Command(
        name="system.theme.apply", source="test",
        params={"name": "cyber"},
    ))
    assert "applied" in result.get("message", "")
    assert theme_mgr.current_name == "cyber"


def test_theme_not_found(tmp_path):
    c, _, cmd_bus, _, _, _ = _make_container(tmp_path)
    _init_plugin(c)
    result = cmd_bus.dispatch_sync(Command(
        name="system.theme.apply", source="test",
        params={"name": "nonexistent"},
    ))
    assert "not found" in result.get("message", "")


def test_theme_no_name(tmp_path):
    c, _, cmd_bus, _, _, _ = _make_container(tmp_path)
    _init_plugin(c)
    result = cmd_bus.dispatch_sync(Command(
        name="system.theme.apply", source="test", params={},
    ))
    assert "Usage" in result.get("message", "")
