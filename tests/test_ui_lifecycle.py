"""UI-0 — Desktop-Normal UX + Background Capability.

Proves the architectural invariant:
    UI visibility must NOT determine Aether runtime lifecycle.

Normal boot = UI visible (desktop-app behavior).
--background = UI hidden, runtime active.
Hide = UI hidden, runtime active.
Quit = real graceful shutdown.

Scope (UI-0 only):
    - default config start_visible=true (desktop normal)
    - --background overrides config -> hidden
    - GUI can initialize without showing the window
    - core services remain initialized/running while UI hidden
    - no Vision/CV behavior changes
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aether.core.event_bus_v2 import EventBus

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _flush(bus: EventBus) -> None:
    bus.flush()
    bus.flush()


def _make_container(tmp_path, *, with_broker=False, start_visible=None):
    from aether.core.command_bus import CommandBus
    from aether.core.result_pipeline import ResultPipeline
    from aether.core.service_container import ServiceContainer
    from aether.ui.hud_manager import HUDManager
    from aether.ui.overlay_model import OverlayModel
    from aether.ui.panel.notification_manager import NotificationManager
    from aether.ui.panel.panel_info import PanelInfo
    from aether.ui.panel.panel_registry import PanelRegistry
    from aether.ui.ui_context import UIContext
    from aether.workspace.workspace_manager import WorkspaceManager

    bus = EventBus()
    pipeline = ResultPipeline(bus)
    command_bus = CommandBus(pipeline)

    registry = PanelRegistry(event_bus=bus)
    registry.register(PanelInfo(id="camera_panel", type="camera", label="Camera",
                                x=0, y=0, w=1920, h=540, visible=True))
    registry.register(PanelInfo(id="memory", type="memory", label="Memory",
                                x=0, y=0, w=400, h=300, visible=True))
    registry.register(PanelInfo(id="ai_chat", type="ai_chat", label="AI Chat",
                                x=0, y=0, w=400, h=300, visible=True))
    registry.register(PanelInfo(id="tasks", type="tasks", label="Tasks",
                                x=0, y=0, w=400, h=300, visible=True))
    registry.register(PanelInfo(id="dashboard", type="dashboard", label="Dashboard",
                                x=0, y=0, w=400, h=300, visible=True))

    workspaces = tmp_path / "workspaces"
    layouts = tmp_path / "layouts"
    workspaces.mkdir(exist_ok=True)
    layouts.mkdir(exist_ok=True)
    (workspaces / "hand.yaml").write_text("default_layout: hand\npanels: []", encoding="utf-8")
    (layouts / "hand.json").write_text('{"name": "hand", "panels": []}', encoding="utf-8")
    wm = WorkspaceManager(registry, workspaces_dir=workspaces, layouts_dir=layouts)
    notification_manager = NotificationManager(bus)

    class _FakeConfig:
        def get(self, key, default=None):
            cfg = {
                "app.mode": "vision",
                "gui.status_bar": {"height": 28},
                "gui.notifications": {"max_visible": 3, "auto_dismiss_ms": 4000,
                                      "position": "bottom_right", "spacing": 8},
            }
            if start_visible is not None:
                cfg["gui.start_visible"] = start_visible
            return cfg.get(key, default)

    container = ServiceContainer()
    container.register_instance("event_bus", bus)
    container.register_instance("command_bus", command_bus)
    container.register_instance("config", _FakeConfig())
    container.register_instance("panel_registry", registry)
    container.register_instance("workspace_manager", wm)
    container.register_instance("notification_manager", notification_manager)

    if with_broker:
        import numpy as np

        class _FakeBroker:
            def __init__(self):
                self._frame = np.zeros((120, 160, 3), dtype=np.uint8)
                self._frame_id = 0

            def get_frame(self):
                self._frame_id += 1
                return self._frame

            def get_frame_id(self):
                return self._frame_id

        container.register_instance("frame_broker", _FakeBroker())

    hud = HUDManager()
    overlay = OverlayModel()
    context = UIContext.from_container(container, overlay_model=overlay, hud_manager=hud)
    return container, context, bus


# --- Default configuration --------------------------------------------


class TestDefaultConfig:
    def test_start_visible_defaults_true(self):
        from aether.config.loader import ConfigLoader
        loader = ConfigLoader(str(ROOT / "config" / "default.yaml"))
        loader.load()
        assert loader.get("gui.start_visible", False) is True

    def test_system_tray_defaults_false(self):
        from aether.config.loader import ConfigLoader
        loader = ConfigLoader(str(ROOT / "config" / "default.yaml"))
        loader.load()
        assert loader.get("gui.system_tray", True) is False

    def test_hotkey_toggle_default(self):
        from aether.config.loader import ConfigLoader
        loader = ConfigLoader(str(ROOT / "config" / "default.yaml"))
        loader.load()
        assert loader.get("gui.hotkey_toggle", "") == "ctrl+alt+space"


# --- ConfigLoader.set --------------------------------------------------


class TestConfigLoaderSet:
    def test_set_simple_key(self):
        from aether.config.loader import ConfigLoader
        loader = ConfigLoader(str(ROOT / "config" / "default.yaml"))
        loader.load()
        original = loader.get("gui.start_visible")
        loader.set("gui.start_visible", not original)
        assert loader.get("gui.start_visible") is (not original)

    def test_set_creates_intermediate_dicts(self):
        from aether.config.loader import ConfigLoader
        loader = ConfigLoader(str(ROOT / "config" / "default.yaml"))
        loader.load()
        loader.set("ui.new.nested.key", 42)
        assert loader.get("ui.new.nested.key") == 42


# --- UIShell build with show_window ------------------------------------


class TestUIShellBackground:
    def test_build_show_window_false_creates_hidden_shell(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell
        shell = UIShell(UIContext())
        shell.build(app=qapp, vision_mode=False, show_window=False)
        assert shell.window is not None
        assert shell.is_running
        assert not shell.window.isVisible()

    def test_build_default_preserves_backward_compat(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell
        shell = UIShell(UIContext())
        shell.build(app=qapp, vision_mode=False)
        assert shell.window is not None
        assert shell.is_running
        assert shell.window.isVisible()

    def test_build_show_window_true_shows(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell
        shell = UIShell(UIContext())
        shell.build(app=qapp, vision_mode=False, show_window=True)
        assert shell.window.isVisible()


# --- GUIPlugin start visibility ----------------------------------------


class TestGUIPluginBackground:
    def test_start_visible_when_config_true(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=True)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        try:
            assert plugin._shell is not None
            assert plugin._running
            assert plugin._shell.window.isVisible()
        finally:
            plugin.stop()
            _flush(bus)

    def test_start_hidden_when_config_false(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=False)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        try:
            assert not plugin._shell.window.isVisible()
        finally:
            plugin.stop()
            _flush(bus)

    def test_start_hidden_when_config_key_absent(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=None)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        try:
            assert plugin._shell is not None
            assert plugin._running
            assert not plugin._shell.window.isVisible()
        finally:
            plugin.stop()
            _flush(bus)

    def test_core_services_remain_when_ui_hidden(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=False)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        try:
            assert not plugin._shell.window.isVisible()
            assert container.has("event_bus")
            assert container.has("command_bus")
            assert container.resolve("event_bus") is bus
            assert container.resolve("command_bus") is not None
            assert plugin._overlay_model is not None
            assert plugin._hud_manager is not None
        finally:
            plugin.stop()
            _flush(bus)

    def test_core_services_remain_when_ui_visible(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=True)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        try:
            assert plugin._shell.window.isVisible()
            assert container.has("event_bus")
            assert container.has("command_bus")
        finally:
            plugin.stop()
            _flush(bus)


# --- Vision integration unchanged --------------------------------------


class TestVisionLifecycleUnchanged:
    def test_camera_widget_created_when_window_hidden(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell
        container, context, bus = _make_container(tmp_path, with_broker=True)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True, show_window=False)
        _flush(bus)
        try:
            assert not shell.window.isVisible()
            assert shell.camera is not None
            assert shell.camera_state is not None
            assert shell.is_running
        finally:
            shell.shutdown()
            _flush(bus)


# --- AetherApplication --background override ---------------------------


class TestBackgroundOverride:
    def test_background_flag_forces_hidden(self):
        from aether.core.application import AetherApplication
        app = AetherApplication(background=True)
        app.boot()
        try:
            gui = [p for p in app.plugin_loader.loaded_plugins if p.name == "gui_plugin"]
            assert gui and gui[0]._shell is not None
            assert not gui[0]._shell.window.isVisible()
            assert app.container.has("event_bus")
            assert app.container.has("command_bus")
        finally:
            app.shutdown()

    def test_no_background_flag_shows_window(self):
        from aether.core.application import AetherApplication
        app = AetherApplication(background=False)
        app.boot()
        try:
            gui = [p for p in app.plugin_loader.loaded_plugins if p.name == "gui_plugin"]
            assert gui and gui[0]._shell is not None
            assert gui[0]._shell.window.isVisible()
        finally:
            app.shutdown()


# --- Full boot proof ---------------------------------------------------


class TestFullBoot:
    def test_boot_ui_visible_core_running(self):
        from aether.core.application import AetherApplication
        app = AetherApplication()
        app.boot()
        try:
            names = {p.name for p in app.plugin_loader.loaded_plugins}
            assert "gui_plugin" in names
            assert {"memory_plugin", "ai_plugin", "keyboard_input_plugin"} <= names

            gui = [p for p in app.plugin_loader.loaded_plugins if p.name == "gui_plugin"]
            assert gui and gui[0]._shell is not None
            shell = gui[0]._shell
            assert shell.is_running
            assert shell.window.isVisible()

            assert app.container.has("event_bus")
            assert app.container.has("command_bus")
            assert app.command_bus is not None
        finally:
            app.shutdown()

    def test_boot_background_ui_hidden_core_running(self):
        from aether.core.application import AetherApplication
        app = AetherApplication(background=True)
        app.boot()
        try:
            names = {p.name for p in app.plugin_loader.loaded_plugins}
            assert "gui_plugin" in names
            assert {"memory_plugin", "ai_plugin", "keyboard_input_plugin"} <= names

            gui = [p for p in app.plugin_loader.loaded_plugins if p.name == "gui_plugin"]
            assert gui and gui[0]._shell is not None
            shell = gui[0]._shell
            assert shell.is_running
            assert not shell.window.isVisible()

            assert app.container.has("event_bus")
            assert app.container.has("command_bus")
            assert app.command_bus is not None
        finally:
            app.shutdown()


# ── UI-1: Runtime Show / Hide API ───────────────────────────────────


class TestUIShellShowHideAPI:
    """UI-1: UIShell runtime visibility methods."""

    def test_show_makes_window_visible(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell
        shell = UIShell(UIContext())
        shell.build(app=qapp, vision_mode=False, show_window=False)
        assert not shell.window.isVisible()
        shell.show()
        assert shell.window.isVisible()
        shell.shutdown()

    def test_hide_makes_window_hidden(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell
        shell = UIShell(UIContext())
        shell.build(app=qapp, vision_mode=False, show_window=True)
        assert shell.window.isVisible()
        shell.hide()
        assert not shell.window.isVisible()
        shell.shutdown()

    def test_toggle_switches_visibility(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell
        shell = UIShell(UIContext())
        shell.build(app=qapp, vision_mode=False, show_window=False)
        assert not shell.window.isVisible()
        shell.toggle()
        assert shell.window.isVisible()
        shell.toggle()
        assert not shell.window.isVisible()
        shell.shutdown()

    def test_is_visible_reports_correct_state(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell
        shell = UIShell(UIContext())
        shell.build(app=qapp, vision_mode=False, show_window=False)
        assert shell.is_visible is False
        shell.show()
        assert shell.is_visible is True
        shell.hide()
        assert shell.is_visible is False
        shell.shutdown()


class TestGUIPluginShowHideAPI:
    """UI-1: GUIPlugin show/hide/toggle/is_ui_visible methods."""

    def test_show_ui_shows_window(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=False)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        try:
            assert not plugin._shell.window.isVisible()
            result = plugin.show_ui()
            assert result["message"] == "UI shown"
            assert plugin._shell.window.isVisible()
        finally:
            plugin.stop()
            _flush(bus)

    def test_hide_ui_hides_window(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=True)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        try:
            assert plugin._shell.window.isVisible()
            result = plugin.hide_ui()
            assert result["message"] == "UI hidden"
            assert not plugin._shell.window.isVisible()
        finally:
            plugin.stop()
            _flush(bus)

    def test_toggle_ui_toggles_window(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=False)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        try:
            assert not plugin._shell.window.isVisible()
            result = plugin.toggle_ui()
            assert "visible" in result["message"]
            assert plugin._shell.window.isVisible()
            result = plugin.toggle_ui()
            assert "hidden" in result["message"]
            assert not plugin._shell.window.isVisible()
        finally:
            plugin.stop()
            _flush(bus)

    def test_is_ui_visible_reports_state(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=False)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        try:
            result = plugin.is_ui_visible()
            assert result["message"] == "hidden"
            plugin.show_ui()
            result = plugin.is_ui_visible()
            assert result["message"] == "visible"
        finally:
            plugin.stop()
            _flush(bus)


class TestShellCommands:
    """UI-1: ui.shell.* command routing through CommandBus."""

    def _make_plugin(self, tmp_path, start_visible=False):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, start_visible=start_visible)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()
        return plugin, container, bus

    def test_shell_show_command(self, qapp, tmp_path):
        from aether.core.command import Command
        plugin, container, bus = self._make_plugin(tmp_path, start_visible=False)
        try:
            cmd_bus = container.resolve("command_bus")
            result = cmd_bus.dispatch_sync(Command(
                name="ui.shell.show", source="test",
            ))
            assert result["message"] == "UI shown"
            assert plugin._shell.window.isVisible()
        finally:
            plugin.stop()
            _flush(bus)

    def test_shell_hide_command(self, qapp, tmp_path):
        from aether.core.command import Command
        plugin, container, bus = self._make_plugin(tmp_path, start_visible=True)
        try:
            cmd_bus = container.resolve("command_bus")
            result = cmd_bus.dispatch_sync(Command(
                name="ui.shell.hide", source="test",
            ))
            assert result["message"] == "UI hidden"
            assert not plugin._shell.window.isVisible()
        finally:
            plugin.stop()
            _flush(bus)

    def test_shell_toggle_command(self, qapp, tmp_path):
        from aether.core.command import Command
        plugin, container, bus = self._make_plugin(tmp_path, start_visible=False)
        try:
            cmd_bus = container.resolve("command_bus")
            result = cmd_bus.dispatch_sync(Command(
                name="ui.shell.toggle", source="test",
            ))
            assert "visible" in result["message"]
            assert plugin._shell.window.isVisible()
        finally:
            plugin.stop()
            _flush(bus)

    def test_shell_is_visible_command(self, qapp, tmp_path):
        from aether.core.command import Command
        plugin, container, bus = self._make_plugin(tmp_path, start_visible=False)
        try:
            cmd_bus = container.resolve("command_bus")
            result = cmd_bus.dispatch_sync(Command(
                name="ui.shell.is_visible", source="test",
            ))
            assert result["message"] == "hidden"
        finally:
            plugin.stop()
            _flush(bus)
