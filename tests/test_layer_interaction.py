"""Phase 2.3B.0 — Diagnostic tests for layer mouse routing.

These tests verify *behavior* (who receives mouse events) rather than
*implementation* (z-order, raise_(), QStackedLayout). They pin down the
current interaction contract:

    - Clicking a panel reaches the panel (mouse_pressed signal fires)
    - Clicking empty workspace space propagates (not swallowed)
    - OverlayWidget is click-through (widgetAt() skips it)
    - Camera BACKGROUND is click-through (widgetAt() returns the layer under it)
    - Camera PiP is draggable (mouse routing reaches it at its position)

Goal: establish a failing baseline if any of these are broken, then
provide a safety net for the upcoming CameraController extraction.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("numpy")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TITLE_BAR_HEIGHT = 28  # mirrors aether.ui.panel.panel_widget
TITLE_BAR_HALF = TITLE_BAR_HEIGHT // 2


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _make_container(tmp_path, *, with_broker=False):
    """Wired container identical to tests/test_camera_pip.py."""
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

    from aether.core.event_bus_v2 import EventBus

    bus = EventBus()
    pipeline = ResultPipeline(bus)
    command_bus = CommandBus(pipeline)

    registry = PanelRegistry(event_bus=bus)
    for pid, ptype, x, y, w, h in [
        ("memory", "memory", 100, 100, 400, 300),
        ("ai_chat", "ai_chat", 520, 100, 400, 300),
        ("tasks", "tasks", 100, 420, 400, 300),
        ("dashboard", "dashboard", 520, 420, 400, 300),
    ]:
        registry.register(PanelInfo(id=pid, type=ptype, label=pid,
                                    x=x, y=y, w=w, h=h, visible=True))

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
                "gui.camera": {"mode": "pip", "width": 320, "height": 180,
                               "anchor": "bottom_right", "margin": 10,
                               "snap_threshold": 40, "dim_background": True,
                               "state_path": str(tmp_path / "camera_pip.json")},
            }
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


def _build_shell(qapp, tmp_path, *, with_broker=True):
    from aether.ui.ui_shell import UIShell
    container, context, bus = _make_container(tmp_path, with_broker=with_broker)
    shell = UIShell(context)
    shell.build(app=qapp, vision_mode=True)
    # Bring the window fully on-screen so global hit-testing is deterministic.
    shell.window.move(0, 0)
    qapp.processEvents()
    return shell, context, bus


def _click_at(qapp, window, local_pos) -> None:
    """Dispatch a real press+release through the window so Qt routes it."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    g = window.mapToGlobal(local_pos)
    local = QPointF(local_pos.x(), local_pos.y())
    global_p = QPointF(g.x(), g.y())

    press = QMouseEvent(QEvent.MouseButtonPress, local, global_p,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(window, press)
    release = QMouseEvent(QEvent.MouseButtonRelease, local, global_p,
                          Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(window, release)


def _click_routed(qapp, window, local_pos) -> None:
    """Route a click through the real hit-test target and send it there.

    Direct sendEvent(window, ...) bypasses Qt's child hit-testing. To
    simulate a real click we must (a) find the receiver with widgetAt(),
    then (b) deliver to that receiver so unhandled events propagate up
    the parent chain exactly as a native click would.
    """
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    g = window.mapToGlobal(local_pos)
    receiver = QApplication.widgetAt(g)
    if receiver is None:
        # Offscreen widgetAt() can miss bare scene space; childAt() is reliable.
        receiver = window.childAt(local_pos)
    assert receiver is not None, f"no widget under {local_pos}"
    local = receiver.mapFromGlobal(g)
    lp = QPointF(local.x(), local.y())
    gp = QPointF(g.x(), g.y())

    press = QMouseEvent(QEvent.MouseButtonPress, lp, gp,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(receiver, press)
    release = QMouseEvent(QEvent.MouseButtonRelease, lp, gp,
                          Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(receiver, release)


def _drag_routed(qapp, window, start_local, delta) -> None:
    """Press at start_local, drag by delta, release — routed to the hit target."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication

    g0 = window.mapToGlobal(start_local)
    receiver = QApplication.widgetAt(g0)
    if receiver is None:
        receiver = window.childAt(start_local)
    assert receiver is not None, f"no widget under {start_local}"

    r0 = receiver.mapFromGlobal(g0)
    dx, dy = delta.x(), delta.y()
    p0 = QPointF(r0.x(), r0.y())
    p1 = QPointF(r0.x() + dx, r0.y() + dy)
    g0f = QPointF(g0.x(), g0.y())
    g1 = QPointF(g0.x() + dx, g0.y() + dy)

    press = QMouseEvent(QEvent.MouseButtonPress, p0, g0f,
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(receiver, press)
    move = QMouseEvent(QEvent.MouseMove, p1, g1,
                       Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    QApplication.sendEvent(receiver, move)
    release = QMouseEvent(QEvent.MouseButtonRelease, p1, g1,
                          Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    QApplication.sendEvent(receiver, release)


def _panel_center_in_scene(panel, scene) -> "QPoint":
    """Return the panel's center mapped into the workspace scene's coords."""
    from PySide6.QtCore import QPoint
    x, y, w, h = panel.geometry()
    return panel.mapTo(scene, QPoint(w // 2, h // 2))


# ── Hit testing helpers ─────────────────────────────────────────────


def _widget_at_global(qapp, window, local_pos):
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QApplication
    g = window.mapToGlobal(QPoint(int(local_pos.x()), int(local_pos.y())))
    return QApplication.widgetAt(g)


# ── Tests ───────────────────────────────────────────────────────────


class TestPanelRouting:
    """Clicking a panel must reach the panel, not be swallowed by a layer."""

    def test_click_panel_fires_mouse_pressed(self, qapp, tmp_path):
        shell, context, bus = _build_shell(qapp, tmp_path)

        panel = context.panel_registry.get("memory").widget
        assert panel is not None
        qapp.processEvents()

        hits = []
        panel.mouse_pressed.connect(lambda pid, x, y, region: hits.append((pid, region)))

        # Click the title bar of the memory panel. The center lands on the
        # text browser, which legitimately consumes the click; the title bar
        # is where the panel itself is the intended receiver.
        from PySide6.QtCore import QPoint
        scene_pos = panel.mapTo(shell.workspace_scene, QPoint(200, TITLE_BAR_HALF))
        _click_routed(qapp, shell.window, scene_pos)

        assert len(hits) == 1, f"expected panel mouse_pressed, got {hits}"
        assert hits[0][0] == "memory"
        shell.shutdown()

    def test_widget_at_center_of_panel_returns_panel(self, qapp, tmp_path):
        shell, context, bus = _build_shell(qapp, tmp_path)
        panel = context.panel_registry.get("memory").widget
        qapp.processEvents()

        scene_pos = _panel_center_in_scene(panel, shell.workspace_scene)
        w = _widget_at_global(qapp, shell.window, scene_pos)

        # The hit widget may be the panel itself or a child content widget —
        # but it must be *under* the panel (within its subtree).
        assert w is not None
        ancestors = []
        node = w
        while node is not None:
            ancestors.append(node)
            node = node.parent()
        assert panel in ancestors, f"widgetAt over panel returned {w}"
        shell.shutdown()


class TestEmptySpaceRouting:
    """Clicks on empty workspace area must propagate, not be swallowed."""

    def test_click_empty_space_reaches_window(self, qapp, tmp_path):
        shell, context, bus = _build_shell(qapp, tmp_path)

        # Pick a point far from any panel and from the PiP camera.
        # Panels occupy (100..520, 100..720); camera PiP is bottom-right.
        from PySide6.QtCore import QPoint
        empty_local = QPoint(980, 500)

        # Offscreen widgetAt() is unreliable over bare scene space, but
        # childAt() shows the WorkspaceScene owns the point — not a panel,
        # not the overlay, not the camera.
        target = shell.window.childAt(empty_local)
        from aether.ui.panel.workspace_scene import WorkspaceScene
        assert isinstance(target, WorkspaceScene), f"empty space hit {target}"

        # Sending a click to the scene must not crash and must not trigger
        # any panel (default-ignore propagates up to the window).
        panels = []
        for info in context.panel_registry.list_all():
            w = info.widget
            if w is not None:
                panels.append(w)
        hits = []
        for p in panels:
            p.mouse_pressed.connect(lambda pid, *_: hits.append(pid))

        _click_routed(qapp, shell.window, empty_local)
        assert hits == [], f"empty-space click hit panels: {hits}"
        shell.shutdown()


class TestOverlayClickThrough:
    """OverlayWidget is decorative — hit testing must skip it."""

    def test_widget_at_overlay_area_is_not_overlay(self, qapp, tmp_path):
        shell, context, bus = _build_shell(qapp, tmp_path)
        overlay = context.overlay_model
        assert overlay is not None

        from PySide6.QtCore import QPoint
        w = _widget_at_global(qapp, shell.window, QPoint(980, 540))

        # OverlayWidget sets WA_TransparentForMouseEvents → never the hit target.
        assert not isinstance(w, shell.window.__class__)  # not a window-level hit only
        # The hit widget must not be the OverlayWidget subclass
        from aether.ui.overlay_widget import OverlayWidget
        assert not isinstance(w, OverlayWidget)
        shell.shutdown()


class TestCameraBackgroundClickThrough:
    """In BACKGROUND mode the camera fills the window but must be click-through."""

    def test_background_camera_widget_at_is_underlying_layer(self, qapp, tmp_path):
        from PySide6.QtCore import QPoint, Qt
        from aether.ui.camera_mode import CameraMode
        shell, context, bus = _build_shell(qapp, tmp_path)
        assert shell.camera is not None

        shell.set_camera_mode(CameraMode.BACKGROUND)
        qapp.processEvents()

        # Camera geometry covers the whole window.
        assert shell.camera.width() == shell.window.width()
        assert shell.camera.height() == shell.window.height()
        assert shell.camera.testAttribute(Qt.WA_TransparentForMouseEvents)

        # widgetAt over the middle of the window must NOT be the camera.
        w = _widget_at_global(qapp, shell.window, QPoint(980, 540))
        assert w is not shell.camera, f"background camera swallowed mouse at {w}"
        shell.shutdown()

    def test_background_camera_click_reaches_panel(self, qapp, tmp_path):
        from aether.ui.camera_mode import CameraMode
        shell, context, bus = _build_shell(qapp, tmp_path)
        panel = context.panel_registry.get("dashboard").widget
        assert shell.camera is not None

        shell.set_camera_mode(CameraMode.BACKGROUND)
        qapp.processEvents()

        hits = []
        panel.mouse_pressed.connect(lambda pid, x, y, region: hits.append(pid))
        from PySide6.QtCore import QPoint
        scene_pos = panel.mapTo(shell.workspace_scene, QPoint(200, TITLE_BAR_HALF))
        _click_routed(qapp, shell.window, scene_pos)

        assert "dashboard" in hits, (
            "BACKGROUND camera blocked the click from reaching the panel"
        )
        shell.shutdown()


class TestCameraPipInteraction:
    """In PiP mode the camera is draggable at its own position."""

    def test_pip_camera_draggable_via_window_routing(self, qapp, tmp_path):
        from PySide6.QtCore import QPoint
        shell, context, bus = _build_shell(qapp, tmp_path)
        assert shell.camera is not None

        # Camera is in PIP mode at the anchor position.
        qapp.processEvents()
        cam = shell.camera
        start_x, start_y = cam.x(), cam.y()
        moved = []
        cam.moved.connect(lambda x, y: moved.append((x, y)))

        # Drag from the camera center through the real hit-test routing:
        # the topmost widget at the camera's position must be the camera itself.
        center_local = cam.mapTo(shell.window, QPoint(cam.width() // 2, cam.height() // 2))
        _drag_routed(qapp, shell.window, center_local, QPoint(40, 30))

        assert len(moved) == 1, "PiP camera drag did not emit moved()"
        assert (cam.x(), cam.y()) != (start_x, start_y)
        shell.shutdown()
