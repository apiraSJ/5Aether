"""Tests for Camera PiP feature (Sprint 2.3).

Covers:
    CameraMode / CameraAnchor enums
    CameraState save/load
    CameraWidget toggle / drag / double-click
    UIShell camera modes (pip, background, minimal, hidden)
    UIShell snap + resize reposition
    GUIPlugin ui.camera.* handlers
    HUDManager hasattr guard (QWidget without paint())
"""

from __future__ import annotations

import os

import pytest

from aether.core.event_bus_v2 import Event, EventBus

pytest.importorskip("PySide6")
pytest.importorskip("numpy")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _flush(bus: EventBus) -> None:
    bus.flush()
    bus.flush()


class _FakeBroker:
    """Minimal FrameBroker stub returning a small test frame."""
    def __init__(self):
        import numpy as np
        self._frame = np.zeros((120, 160, 3), dtype=np.uint8)
        self._frame_id = 0

    def get_frame(self):
        self._frame_id += 1
        return self._frame

    def get_frame_id(self):
        return self._frame_id


def _make_container(tmp_path, *, with_broker=False):
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
        def __init__(self, camera_state_path=None):
            self._camera_state_path = camera_state_path
        def get(self, key, default=None):
            cfg = {
                "app.mode": "vision",
                "gui.status_bar": {"height": 28},
                "gui.notifications": {"max_visible": 3, "auto_dismiss_ms": 4000,
                                      "position": "bottom_right", "spacing": 8},
                "gui.camera": {"mode": "pip", "width": 320, "height": 180,
                               "anchor": "bottom_right", "margin": 10,
                               "snap_threshold": 40, "dim_background": True,
                               "state_path": str(self._camera_state_path) if self._camera_state_path else None},
            }
            return cfg.get(key, default)

    camera_state_path = tmp_path / "camera_pip.json"
    container = ServiceContainer()
    container.register_instance("event_bus", bus)
    container.register_instance("command_bus", command_bus)
    container.register_instance("config", _FakeConfig(camera_state_path=camera_state_path))
    container.register_instance("panel_registry", registry)
    container.register_instance("workspace_manager", wm)
    container.register_instance("notification_manager", notification_manager)

    if with_broker:
        container.register_instance("frame_broker", _FakeBroker())

    hud = HUDManager()
    overlay = OverlayModel()
    context = UIContext.from_container(container, overlay_model=overlay, hud_manager=hud)
    return container, context, bus


# ── Enums ──────────────────────────────────────────────────────────


class TestCameraMode:
    def test_from_str(self):
        from aether.ui.camera_mode import CameraMode
        assert CameraMode.from_str("pip") == CameraMode.PIP
        assert CameraMode.from_str("BACKGROUND") == CameraMode.BACKGROUND
        assert CameraMode.from_str("unknown") == CameraMode.PIP  # default

    def test_values(self):
        from aether.ui.camera_mode import CameraMode
        assert CameraMode.PIP.value == "pip"
        assert CameraMode.BACKGROUND.value == "background"
        assert CameraMode.MINIMAL.value == "minimal"
        assert CameraMode.HIDDEN.value == "hidden"


class TestCameraAnchor:
    def test_from_str(self):
        from aether.ui.camera_anchor import CameraAnchor
        assert CameraAnchor.from_str("top_left") == CameraAnchor.TOP_LEFT
        assert CameraAnchor.from_str("FREE") == CameraAnchor.FREE
        assert CameraAnchor.from_str("bogus") == CameraAnchor.BOTTOM_RIGHT  # default

    def test_values(self):
        from aether.ui.camera_anchor import CameraAnchor
        assert CameraAnchor.BOTTOM_RIGHT.value == "bottom_right"
        assert CameraAnchor.FREE.value == "free"


# ── CameraState ────────────────────────────────────────────────────


class TestCameraState:
    def test_save_load_roundtrip(self, tmp_path):
        from aether.ui.camera_state import CameraState
        from aether.ui.camera_mode import CameraMode
        from aether.ui.camera_anchor import CameraAnchor

        state = CameraState(mode=CameraMode.PIP, anchor=CameraAnchor.TOP_RIGHT,
                            x=100, y=200, width=320, height=180)
        path = tmp_path / "camera.json"
        state.save(path)

        loaded = CameraState.load(path)
        assert loaded.mode == CameraMode.PIP
        assert loaded.anchor == CameraAnchor.TOP_RIGHT
        assert loaded.x == 100
        assert loaded.y == 200
        assert loaded.width == 320
        assert loaded.height == 180

    def test_load_missing_returns_defaults(self, tmp_path):
        from aether.ui.camera_state import CameraState
        from aether.ui.camera_mode import CameraMode
        loaded = CameraState.load(tmp_path / "nonexistent.json")
        assert loaded.mode == CameraMode.PIP
        assert loaded.anchor.value == "bottom_right"


# ── CameraWidget ───────────────────────────────────────────────────


class TestCameraWidget:
    def test_toggle(self, qapp):
        from aether.ui.camera_widget import CameraWidget
        cam = CameraWidget(_FakeBroker())
        cam.show()
        assert cam.is_visible()
        cam.toggle()
        assert not cam.is_visible()
        cam.toggle()
        assert cam.is_visible()
        cam.stop()

    def test_drag_emits_moved(self, qapp):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, QPointF, QPoint
        from aether.ui.camera_widget import CameraWidget

        cam = CameraWidget(_FakeBroker())
        cam.set_drag_enabled(True)
        cam.show()
        cam.setGeometry(100, 100, 320, 180)

        results = []
        cam.moved.connect(lambda x, y: results.append((x, y)))

        # Press at (50, 50) local
        press = QMouseEvent(QEvent.MouseButtonPress, QPointF(50, 50),
                            QPointF(50, 50), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        cam.mousePressEvent(press)

        # Move to (80, 120) local
        move = QMouseEvent(QEvent.MouseMove, QPointF(80, 120),
                           QPointF(80, 120), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        cam.mouseMoveEvent(move)

        # Release
        release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(80, 120),
                              QPointF(80, 120), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        cam.mouseReleaseEvent(release)

        assert len(results) == 1
        assert results[0] == (cam.x(), cam.y())
        cam.stop()

    def test_double_click_signal(self, qapp):
        from PySide6.QtCore import Qt, QPointF, QEvent
        from PySide6.QtGui import QMouseEvent
        from aether.ui.camera_widget import CameraWidget

        cam = CameraWidget(_FakeBroker())
        clicked = []
        cam.double_clicked.connect(lambda: clicked.append(True))

        event = QMouseEvent(QEvent.MouseButtonDblClick, QPointF(10, 10),
                            QPointF(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        cam.mouseDoubleClickEvent(event)
        assert clicked == [True]
        cam.stop()


# ── UIShell camera modes ───────────────────────────────────────────


class TestUIShellCamera:
    def test_pip_mode_creates_camera(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell
        container, context, bus = _make_container(tmp_path, with_broker=True)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)

        assert shell.camera is not None
        assert shell.camera.isVisible()
        assert shell.camera_state is not None
        from aether.ui.camera_mode import CameraMode
        assert shell.camera_state.mode == CameraMode.PIP
        # Camera is a direct window child (not in the stacked layout)
        assert shell.camera.parent() is shell.window
        shell.shutdown()

    def test_hidden_mode(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell
        from aether.ui.camera_mode import CameraMode
        container, context, bus = _make_container(tmp_path, with_broker=True)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)

        shell.set_camera_mode(CameraMode.HIDDEN)
        assert not shell.camera.isVisible()
        assert shell.camera_state.mode == CameraMode.HIDDEN
        shell.shutdown()

    def test_background_mode(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell
        from aether.ui.camera_mode import CameraMode
        container, context, bus = _make_container(tmp_path, with_broker=True)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)

        shell.set_camera_mode(CameraMode.BACKGROUND)
        assert shell.camera_state.mode == CameraMode.BACKGROUND
        assert shell.camera.width() == shell.window.width()
        assert shell.camera.height() == shell.window.height()
        shell.shutdown()

    def test_toggle_camera(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell
        from aether.ui.camera_mode import CameraMode
        container, context, bus = _make_container(tmp_path, with_broker=True)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)

        assert shell.camera_state.mode == CameraMode.PIP
        shell.toggle_camera()
        assert shell.camera_state.mode == CameraMode.BACKGROUND
        shell.toggle_camera()
        assert shell.camera_state.mode == CameraMode.PIP
        shell.shutdown()

    def test_parent_unchanged_after_mode_switch(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell
        from aether.ui.camera_mode import CameraMode
        container, context, bus = _make_container(tmp_path, with_broker=True)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)

        original_parent = shell.camera.parent()
        for mode in [CameraMode.BACKGROUND, CameraMode.PIP, CameraMode.MINIMAL, CameraMode.HIDDEN, CameraMode.PIP]:
            shell.set_camera_mode(mode)
        assert shell.camera.parent() is original_parent
        shell.shutdown()

    def test_resize_repositions_pip(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell
        container, context, bus = _make_container(tmp_path, with_broker=True)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)

        before_x = shell.camera.x()
        before_y = shell.camera.y()
        shell.window.resize(800, 600)
        shell._layout_shell()
        # Camera should have moved (clamped into smaller window)
        assert shell.camera.x() != before_x or shell.camera.y() != before_y
        shell.shutdown()

    def test_show_camera_from_hidden(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell
        from aether.ui.camera_mode import CameraMode
        container, context, bus = _make_container(tmp_path, with_broker=True)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        _flush(bus)

        shell.hide_camera()
        assert not shell.camera.isVisible()
        shell.show_camera()
        assert shell.camera.isVisible()
        assert shell.camera_state.mode != CameraMode.HIDDEN
        shell.shutdown()

    def test_no_broker_graceful(self, qapp, tmp_path):
        from aether.ui.ui_shell import UIShell
        container, context, bus = _make_container(tmp_path, with_broker=False)
        shell = UIShell(context)
        shell.build(app=qapp, vision_mode=True)
        assert shell.camera is None
        shell.shutdown()


# ── GUIPlugin camera commands ──────────────────────────────────────


class TestGUIPluginCameraCommands:
    def test_toggle_handler(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, with_broker=True)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()

        from aether.core.command import Command
        result = plugin._command_bus.dispatch_sync(Command(
            name="ui.camera.toggle", source="test"))
        assert "Camera" in result["message"]

        plugin.stop()

    def test_mode_handler(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        container, context, bus = _make_container(tmp_path, with_broker=True)
        plugin = GUIPlugin()
        plugin.initialize(container)
        plugin.start()

        from aether.core.command import Command
        result = plugin._command_bus.dispatch_sync(Command(
            name="ui.camera.mode.hidden", source="test"))
        assert "hidden" in result["message"]

        plugin.stop()

    def test_command_registry_has_camera_commands(self, qapp, tmp_path):
        from aether.plugins.gui_plugin import GUIPlugin
        from aether.core.command_registry import CommandRegistry
        container, context, bus = _make_container(tmp_path, with_broker=True)
        # Pre-create CommandRegistry (like SystemCommandPlugin does)
        cr = CommandRegistry()
        cr.initialize(container)
        container.register_instance("command_registry", cr)

        plugin = GUIPlugin()
        plugin.initialize(container)

        cats = cr.get_categories()
        all_cmds = []
        for cat in cats:
            all_cmds.extend(cr.get_commands_in_category(cat))
        assert "ui.camera.toggle" in all_cmds
        assert "ui.camera.mode.pip" in all_cmds


# ── HUDManager hasattr guard ───────────────────────────────────────


class TestHUDManagerGuard:
    def test_plain_qwidget_no_crash(self, qapp):
        from aether.ui.hud_manager import HUDManager
        from PySide6.QtWidgets import QWidget

        hud = HUDManager()
        w = QWidget()
        hud.add_widget(w, layer=0)
        # update + paint should NOT raise
        hud.update()
        hud.paint()
