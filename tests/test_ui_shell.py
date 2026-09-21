"""Tests for Sprint 2.2 — Shell Consolidation (UIContext + UIShell).

Covers:
    UIContext immutability + from_container resolution
    UIShell headless build / shutdown
    UIShell vision build (window, layers, panels, shell chrome, palette)
    End-to-end event flow through the shell (workspace toast, metrics)
    GUIPlugin thin-orchestrator refactor (initialize builds UIContext)
"""

from __future__ import annotations

import os

import pytest

from aether.core.event_bus_v2 import Event, EventBus
from aether.core.event_type import EventType
from aether.core.performance_snapshot import PerformanceSnapshot

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _flush(bus: EventBus) -> None:
    """Flush twice — events published during delivery land on the next flush."""
    bus.flush()
    bus.flush()


def _make_container(tmp_path):
    """A ServiceContainer wired like AetherApp.boot(), plus UI services."""
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
    registry.register(PanelInfo(id="camera_panel", type="camera", label="Camera Feed",
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
    (workspaces / "hand.yaml").write_text(
        "default_layout: hand\npanels: []", encoding="utf-8")
    (layouts / "hand.json").write_text(
        '{"name": "hand", "panels": []}', encoding="utf-8")
    wm = WorkspaceManager(registry, workspaces_dir=workspaces, layouts_dir=layouts)

    notification_manager = NotificationManager(bus)

    class _FakeConfig:
        def get(self, key, default=None):
            config = {
                "app.mode": "vision",
                "gui.status_bar": {"height": 28},
                "gui.notifications": {"max_visible": 3, "auto_dismiss_ms": 4000,
                                      "position": "bottom_right", "spacing": 8},
            }
            return config.get(key, default)

    container = ServiceContainer()
    container.register_instance("event_bus", bus)
    container.register_instance("command_bus", command_bus)
    container.register_instance("config", _FakeConfig())
    container.register_instance("panel_registry", registry)
    container.register_instance("workspace_manager", wm)
    container.register_instance("notification_manager", notification_manager)

    hud = HUDManager()
    overlay = OverlayModel()
    context = UIContext.from_container(container, overlay_model=overlay, hud_manager=hud)
    return container, context, bus


# ── UIContext ──────────────────────────────────────────────────────


class TestUIContext:
    def test_is_frozen(self):
        from dataclasses import FrozenInstanceError

        from aether.ui.ui_context import UIContext
        context = UIContext(command_bus=object())
        with pytest.raises(FrozenInstanceError):
            context.command_bus = None

    def test_from_container_resolves_services(self, tmp_path):
        container, context, bus = _make_container(tmp_path)
        assert context.event_bus is bus
        assert context.command_bus is not None
        assert context.panel_registry is not None
        assert context.workspace_manager is not None
        assert context.notification_manager is not None
        assert context.config is not None
        assert context.overlay_model is not None
        assert context.hud_manager is not None

    def test_optional_fields_default_none(self):
        from aether.ui.ui_context import UIContext
        context = UIContext()
        assert context.command_bus is None
        assert context.memory_service is None
        assert context.container is None


# ── UIShell — headless ─────────────────────────────────────────────


class TestUIShellHeadless:
    def test_build_creates_window(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell

        shell = UIShell(UIContext())
        shell.build(app=qapp, vision_mode=False)
        assert shell.window is not None
        assert shell.window.windowTitle() == "Aether Dashboard"
        assert shell.is_running
        assert shell.workspace_scene is None
        assert shell.palette is None

    def test_shutdown_hides_window_and_stops(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell

        shell = UIShell(UIContext())
        shell.build(app=qapp, vision_mode=False)
        shell.shutdown()
        assert not shell.is_running
        assert not shell.window.isVisible()


# ── UIShell — vision mode ──────────────────────────────────────────


class TestUIShellVision:
    def test_build_creates_all_layers(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell

        container, context, bus = _make_container(tmp_path)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)

        assert shell.window is not None
        assert shell.workspace_scene is not None
        assert shell.status_bar is not None
        assert shell.notification_widget is not None
        assert shell.palette is not None
        assert shell.is_running

        # Panel widgets were created and bound via the factory
        registry = context.panel_registry
        assert registry.get("dashboard").widget is not None
        assert registry.get("memory").widget is not None
        assert registry.get("tasks").widget is not None
        assert registry.get("ai_chat").widget is not None

    def test_workspace_restored_and_announced(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell

        container, context, bus = _make_container(tmp_path)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)

        # Default workspace + layout restored
        assert context.workspace_manager.current_layout == "hand"
        # Boot toast aggregated by NotificationManager → visible on widget
        assert shell.notification_widget.toast_count >= 1

    def test_metrics_flow_to_bound_dashboard(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell

        container, context, bus = _make_container(tmp_path)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)

        dashboard = context.panel_registry.get("dashboard").widget
        bus.publish(Event(type=EventType.SYSTEM_METRICS,
                          payload=PerformanceSnapshot(cpu_percent=42.0),
                          source="test"))
        _flush(bus)
        card = dashboard._cards["cpu_percent"]
        assert card._value_widget.text() == "42"

    def test_memory_event_creates_toast(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell

        container, context, bus = _make_container(tmp_path)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)
        before = shell.notification_widget.toast_count

        bus.publish(Event(type=EventType.MEMORY_CREATED,
                          payload={"title": "Shell Note"}, source="test"))
        _flush(bus)
        assert shell.notification_widget.toast_count == before + 1

    def test_palette_lists_panels(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell

        container, context, bus = _make_container(tmp_path)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        shell.palette.refresh()
        titles = {e.title for e in shell.palette.entries}
        assert {"memory", "dashboard", "tasks", "ai_chat"} <= titles

    def test_shutdown_unwires_and_hides(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell

        container, context, bus = _make_container(tmp_path)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        shell.shutdown()
        assert not shell.is_running
        assert not shell.window.isVisible()
        # NotificationManager no longer receives events
        bus.publish(Event(type=EventType.MEMORY_CREATED,
                          payload={"title": "Late"}, source="test"))
        _flush(bus)
        assert shell.notification_widget.toast_count == 0

    def test_update_drives_hud(self, qapp):
        from aether.ui.ui_context import UIContext
        from aether.ui.ui_shell import UIShell

        class _FakeHud:
            def __init__(self):
                self.updates = 0
                self.paints = 0

            def update(self):
                self.updates += 1

            def paint(self):
                self.paints += 1

            def clear(self):
                pass

        hud = _FakeHud()
        shell = UIShell(UIContext(hud_manager=hud))
        shell.build(app=qapp, vision_mode=False)
        shell.update()
        assert hud.updates == 1
        assert hud.paints == 1


# ── GUIPlugin refactor ─────────────────────────────────────────────


class TestGUIPluginRefactor:
    def test_initialize_builds_context(self, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin

        container, context, bus = _make_container(tmp_path)
        plugin = GUIPlugin()
        plugin.initialize(container)

        assert plugin._context is not None
        assert plugin._context.workspace_manager is plugin._workspace_manager
        assert container.has("workspace_manager")
        assert container.has("notification_manager")
        assert plugin._overlay_model is not None
        assert plugin._hud_manager is not None

    def test_metadata_updated(self):
        from aether.plugins.gui_plugin import GUIPlugin
        assert GUIPlugin().metadata.version == "3.0"
