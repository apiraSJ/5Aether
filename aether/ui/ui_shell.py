"""UIShell — owns the Aether presentation layer.

The UIShell creates and owns every widget that appears on screen:
the vision HUD layers (camera feed, overlay, workspace scene, HUD
widgets), the shell chrome (StatusBar + NotificationWidget), and the
CommandPalette. It also drives the HUD render loop and tears everything
down on shutdown.

It has no DI knowledge beyond the UIContext it is handed:

    GUIPlugin ──builds──> UIContext ──> UIShell ──owns──> widgets
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from aether.core.profiler import profiler
from aether.ui.ui_context import UIContext

logger = logging.getLogger("Aether.UIShell")


class UIShell:
    """Owns creation, layout, rendering, and teardown of all widgets."""

    def __init__(self, context: UIContext) -> None:
        self._context = context
        self._app = None
        self._window = None
        self._workspace_scene = None
        self._palette = None
        self._status_bar = None
        self._notification_widget = None
        self._timeline = None
        self._perf_hud = None
        self._repaint_monitor = None
        self._running = False
        # Camera
        self._camera = None
        self._backdrop = None
        self._scrim = None
        self._camera_state = None

    # ── Public accessors ──────────────────────────────────────────

    @property
    def window(self):
        return self._window

    @property
    def workspace_scene(self):
        return self._workspace_scene

    @property
    def palette(self):
        return self._palette

    @property
    def status_bar(self):
        return self._status_bar

    @property
    def notification_widget(self):
        return self._notification_widget

    @property
    def camera(self):
        return self._camera

    @property
    def camera_state(self):
        return self._camera_state

    @property
    def hud_manager(self):
        return self._context.hud_manager

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Lifecycle ─────────────────────────────────────────────────

    def build(self, app=None, vision_mode: bool = False, show_window: bool = True) -> None:
        """Create the window and every widget for the requested mode.

        `show_window` controls whether the shell window is presented on
        boot. When False the runtime is built but stays background (UI-0:
        UI visibility does not determine Aether runtime lifecycle).
        Defaults to True for backward compatibility.
        """
        self._app = app
        self._vision_mode = vision_mode

        if vision_mode:
            self._build_vision_hud(show_window)
        else:
            self._build_headless_dashboard(show_window)

        self._running = True
        logger.info("UIShell built (vision=%s, visible=%s)", vision_mode, show_window)

    def update(self) -> None:
        """Drive the HUD render pipeline (throttled per layer)."""
        if not self._running:
            return
        hud = self._context.hud_manager
        if hud is not None:
            try:
                hud.update()
                hud.paint()
            except Exception:
                pass
        if self._app is not None:
            t0 = time.perf_counter()
            self._app.processEvents()
            profiler.record_event_loop((time.perf_counter() - t0) * 1000.0)

    def shutdown(self) -> None:
        """Unwire all widgets, persist the layout, and hide the window."""
        self._running = False

        # Persist workspace sessions (event-driven auto-save target)
        if self._workspace_scene is not None:
            try:
                self._workspace_scene.request_layout_save()
            except Exception:
                logger.exception("Failed to save workspace sessions on stop")

        workspace_manager = self._context.workspace_manager
        if workspace_manager is not None:
            try:
                workspace_manager.save_layout("last_session")
            except Exception:
                logger.exception("Failed to save layout on stop")

        # Unwire shell chrome
        if self._status_bar is not None:
            try:
                self._status_bar.unwire()
            except Exception:
                pass
        if self._notification_widget is not None:
            try:
                self._notification_widget.unwire()
                self._notification_widget.clear()
            except Exception:
                pass
        if self._context.notification_manager is not None:
            try:
                self._context.notification_manager.unsubscribe()
            except Exception:
                pass

        # Tear down the HUD presentation layer
        if self._context.overlay_controller is not None:
            try:
                self._context.overlay_controller.unsubscribe()
            except Exception:
                pass
        if self._context.hud_manager is not None:
            try:
                self._context.hud_manager.clear()
            except Exception:
                pass

        # Stop camera and persist PiP state
        if self._camera is not None:
            try:
                self._camera.stop()
                if self._camera_state is not None:
                    self._camera_state.save()
            except Exception:
                pass

        if self._window is not None:
            self._window.hide()
        logger.info("UIShell shutdown complete")

    # ── Vision HUD ────────────────────────────────────────────────

    def _build_vision_hud(self, show_window: bool = True) -> None:
        # Load camera state (file or defaults)
        from aether.ui.camera_state import CameraState
        from pathlib import Path
        state_path = None
        if self._context.config:
            cam_cfg = self._context.config.get("gui.camera") or {}
            sp = cam_cfg.get("state_path")
            if sp:
                state_path = Path(sp)
        self._camera_state = CameraState.load(state_path)

        self._create_window("Aether Vision HUD")
        self._create_backdrop()
        self._create_vision_layers()
        self._create_camera()
        self._create_statusbar()
        self._create_notifications()
        self._create_palette()
        self._restore_workspace()
        self._apply_camera_mode(self._camera_state.mode)
        self._layout_shell()
        self._install_event_filter()
        self._wire_palette()
        if show_window:
            self._window.show()
        logger.info("Vision HUD created (%d widgets, %d layers, %d panels, camera=%s, visible=%s)",
                    self._context.hud_manager.widget_count if self._context.hud_manager else 0,
                    len(self._context.hud_manager.layers) if self._context.hud_manager else 0,
                    len(self._workspace_scene.window_manager.list_panels())
                    if self._workspace_scene else 0,
                    self._camera_state.mode.value,
                    show_window)

    def _create_window(self, title: str) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget

        window = QWidget()
        window.setWindowTitle(title)
        window.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        window.setAttribute(Qt.WA_TranslucentBackground)
        window.resize(1920, 1080)
        self._window = window

    def _create_backdrop(self) -> None:
        """Dark backdrop — always visible, paints below everything."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget
        from PySide6.QtGui import QColor

        backdrop = QWidget(self._window)
        backdrop.setStyleSheet("background: rgba(10, 12, 20, 230);")
        backdrop.setGeometry(0, 0, self._window.width(), self._window.height())
        backdrop.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # visual only, never blocks panels
        backdrop.lower()  # ensure behind everything
        self._backdrop = backdrop

    def _create_vision_layers(self) -> None:
        """Overlay + WorkspaceScene in a stacked layout (camera is separate)."""
        from PySide6.QtWidgets import QStackedLayout

        layout = QStackedLayout(self._window)
        layout.setStackingMode(QStackedLayout.StackAll)
        context = self._context

        # Vision overlay (objects, hands, cursor)
        from aether.ui.overlay_widget import OverlayWidget
        overlay = OverlayWidget(context.overlay_model)
        layout.addWidget(overlay)
        context.hud_manager.add_widget(overlay, layer=1)

        # Layer 2 — Workspace panels (pure Qt widget, HUDManager does NOT drive it)
        from aether.ui.panel.workspace_scene import WorkspaceScene
        scene = WorkspaceScene(self._window)
        layout.addWidget(scene)
        self._workspace_scene = scene

        self._create_workspace_panels(scene)
        self._wire_memory_controller(scene)

        # Layer 3 — HUD widgets (status, gesture, objects, hand status)
        from aether.ui.status_widget import StatusWidget
        status = StatusWidget(context.overlay_model, self._window)
        status.setGeometry(0, 0, 1920, 28)
        context.hud_manager.add_widget(status, layer=3)

        from aether.ui.object_list_widget import ObjectListWidget
        obj_list = ObjectListWidget(context.overlay_model, self._window)
        obj_list.setGeometry(0, 28, 160, 400)
        context.hud_manager.add_widget(obj_list, layer=3)

        from aether.ui.gesture_widget import GestureWidget
        gesture = GestureWidget(context.overlay_model, self._window)
        gesture.setGeometry(0, 1048, 1920, 32)
        context.hud_manager.add_widget(gesture, layer=3)

        from aether.ui.hand_status_widget import HandStatusWidget
        hand_status = HandStatusWidget(context.overlay_model, self._window)
        hand_status.setGeometry(1700, 28, 160, 100)
        context.hud_manager.add_widget(hand_status, layer=3)

        # Layer 4 — Debug (timeline, perf HUD)
        from aether.ui.timeline_widget import TimelineWidget
        timeline = TimelineWidget(context.overlay_model, self._window)
        timeline.setGeometry(1700, 140, 160, 400)
        timeline.hide()
        context.hud_manager.add_widget(timeline, layer=4)
        self._timeline = timeline

        from aether.ui.performance_hud import PerformanceHUD
        perf_hud = PerformanceHUD(self._window)
        perf_hud.setGeometry(0, 620, 300, 460)
        context.hud_manager.add_widget(perf_hud, layer=4)
        self._perf_hud = perf_hud

        # Count Qt repaints across the whole window subtree
        from aether.ui.repaint_monitor import RepaintMonitor
        self._repaint_monitor = RepaintMonitor(self._window)

        # Position top-right of screen
        if self._app is not None and self._app.primaryScreen() is not None:
            screen = self._app.primaryScreen().geometry()
            self._window.move(screen.width() - 1960, 20)

    def _create_workspace_panels(self, scene) -> None:
        """Instantiate registered panel widgets, bind the UIContext, and add them."""
        from aether.ui.panel.widget_factory import WidgetFactory

        factory = WidgetFactory()
        for info in self._context.panel_registry.list_all():
            if info.id == "camera_panel":
                continue  # Camera is a separate widget in layer 0
            widget = factory.create_widget(info, scene)
            if widget is None:
                continue
            if hasattr(widget, "bind_context"):
                widget.bind_context(self._context)
            info.widget = widget
            scene.add_panel(widget)
            if hasattr(widget, "bind_session"):
                session = scene.get_session(info.id)
                if session is not None:
                    widget.bind_session(session)

    def _wire_memory_controller(self, scene) -> None:
        """Attach the functional MemoryService via a MemoryController."""
        context = self._context
        if context.memory_service is None:
            logger.debug("MemoryService not available; memory panel stays inert")
            return
        try:
            from aether.ui.panel.memory_controller import MemoryController
            from aether.ui.panel.panel_session import PanelSession

            for info in context.panel_registry.list_all():
                if info.type != "memory" or info.widget is None:
                    continue
                widget = info.widget
                session = scene.get_session(info.id)
                if session is None:
                    session = PanelSession(panel_id=info.id, panel_type=info.type)
                    scene.restore_sessions([session.serialize()])
                controller = MemoryController(session, service=context.memory_service)
                controller.wire_services(context.command_bus, context.event_bus)
                widget.wire_controller(controller)
                logger.info("MemoryController wired to panel '%s'", info.id)
                return
        except Exception:
            logger.exception("Failed to wire memory controller")

    # ── Camera ────────────────────────────────────────────────────

    def _create_camera(self) -> None:
        """Create CameraWidget as a direct window child (not in any layout)."""
        context = self._context
        broker = None
        if context.container is not None and context.container.has("frame_broker"):
            broker = context.container.resolve("frame_broker")
        if broker is None:
            logger.debug("FrameBroker not available; camera disabled")
            return
        from aether.ui.camera_widget import CameraWidget
        cam = CameraWidget(broker, self._window)
        cam.hide()
        cam.set_drag_enabled(True)
        cam.moved.connect(self._on_camera_moved)
        cam.double_clicked.connect(lambda: self.toggle_camera())
        self._camera = cam
        logger.info("CameraWidget created")

    def _apply_camera_mode(self, mode) -> None:
        """Apply camera presentation mode without re-parenting."""
        from PySide6.QtCore import Qt
        from aether.ui.camera_mode import CameraMode
        from aether.ui.camera_anchor import CameraAnchor

        if self._camera is None:
            return

        self._camera_state.mode = mode

        if mode == CameraMode.BACKGROUND:
            self._camera.setGeometry(0, 0, self._window.width(), self._window.height())
            self._camera.setAttribute(Qt.WA_TransparentForMouseEvents)
            self._camera.stackUnder(self._window.findChild(type(self._window)))
            # stackUnder overlay — find it from the layout
            self._position_camera_behind_overlay()
            self._camera.show()
            self._camera.setStyleSheet("background:transparent; border-radius:0px;")
            self._apply_scrim(True)
        elif mode == CameraMode.PIP:
            self._camera.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._apply_pip_geometry(self._camera_state.width, self._camera_state.height)
            self._camera.raise_()
            self._camera.show()
            self._camera.setStyleSheet(
                "background:transparent; border-radius:8px; border: 1px solid rgba(255,255,255,40);"
            )
            self._apply_shadow(True)
            self._apply_scrim(False)
        elif mode == CameraMode.MINIMAL:
            self._camera.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._apply_pip_geometry(160, 90)
            self._camera.raise_()
            self._camera.show()
            self._camera.setStyleSheet(
                "background:transparent; border-radius:4px; border: 1px solid rgba(255,255,255,30);"
            )
            self._apply_shadow(False)
            self._apply_scrim(False)
        elif mode == CameraMode.HIDDEN:
            self._camera.hide()
            self._apply_scrim(False)
            self._apply_shadow(False)

        self._camera_state.save()
        logger.info("Camera mode: %s", mode.value)

    def _position_camera_behind_overlay(self) -> None:
        """Stack camera behind the overlay widget (background mode)."""
        from PySide6.QtWidgets import QStackedLayout
        layout = self._window.layout()
        if isinstance(layout, QStackedLayout) and layout.count() > 0:
            overlay = layout.widget(0)
            if overlay is not None:
                self._camera.stackUnder(overlay)

    def _apply_pip_geometry(self, width: int, height: int) -> None:
        """Position camera at the current anchor, clamped to window bounds."""
        from aether.ui.camera_anchor import CameraAnchor
        state = self._camera_state
        margin = self._get_config_margin()
        ww = self._window.width()
        wh = self._window.height()

        if state.anchor == CameraAnchor.FREE and state.x >= 0 and state.y >= 0:
            x = max(margin, min(state.x, ww - width - margin))
            y = max(margin, min(state.y, wh - height - margin))
        else:
            x, y = self._anchor_position(state.anchor, width, height, ww, wh, margin)

        self._camera.setGeometry(x, y, width, height)
        self._camera_state.x = x
        self._camera_state.y = y
        self._camera_state.width = width
        self._camera_state.height = height

    def _anchor_position(self, anchor, w, h, ww, wh, margin) -> tuple[int, int]:
        """Compute x, y for a given anchor and size."""
        from aether.ui.camera_anchor import CameraAnchor
        if anchor == CameraAnchor.TOP_LEFT:
            return margin, margin
        elif anchor == CameraAnchor.TOP_RIGHT:
            return ww - w - margin, margin
        elif anchor == CameraAnchor.BOTTOM_LEFT:
            return margin, wh - h - margin
        else:  # BOTTOM_RIGHT or default
            return ww - w - margin, wh - h - margin

    def _get_config_margin(self) -> int:
        config = self._context.config
        if config:
            cam_cfg = config.get("gui.camera") or {}
            return int(cam_cfg.get("margin", 10))
        return 10

    def _apply_scrim(self, visible: bool) -> None:
        """Show/hide dim scrim (for background mode readability)."""
        config = self._context.config
        dim = True
        if config:
            cam_cfg = config.get("gui.camera") or {}
            dim = bool(cam_cfg.get("dim_background", True))

        if visible and dim:
            if self._scrim is None:
                from PySide6.QtWidgets import QWidget
                from PySide6.QtGui import QColor
                from PySide6.QtCore import Qt
                scrim = QWidget(self._window)
                scrim.setStyleSheet("background: rgba(0, 0, 0, 120);")
                scrim.setGeometry(0, 0, self._window.width(), self._window.height())
                scrim.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # visual only, never blocks panels
                self._scrim = scrim
            self._scrim.setGeometry(0, 0, self._window.width(), self._window.height())
            self._scrim.stackUnder(self._camera)
            self._scrim.show()
        elif self._scrim is not None:
            self._scrim.hide()

    def _apply_shadow(self, enabled: bool) -> None:
        """Add/remove drop shadow on camera PiP."""
        if enabled:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shadow = QGraphicsDropShadowEffect(self._camera)
            shadow.setBlurRadius(12)
            shadow.setColor(QColor(0, 0, 0, 100))
            shadow.setOffset(2, 2)
            self._camera.setGraphicsEffect(shadow)
        else:
            self._camera.setGraphicsEffect(None)

    def _on_camera_moved(self, x: int, y: int) -> None:
        """Handle camera drag release — snap + save."""
        from aether.ui.camera_anchor import CameraAnchor
        state = self._camera_state
        state.x = x
        state.y = y
        state.anchor = self._snap_camera(x, y, state.width, state.height)
        state.save()

    def _snap_camera(self, x: int, y: int, w: int, h: int):
        """Snap to nearest corner if within threshold, else FREE."""
        from aether.ui.camera_anchor import CameraAnchor
        config = self._context.config
        threshold = 40
        if config:
            cam_cfg = config.get("gui.camera") or {}
            threshold = int(cam_cfg.get("snap_threshold", 40))
        margin = self._get_config_margin()
        ww = self._window.width()
        wh = self._window.height()
        corners = {
            CameraAnchor.TOP_LEFT: (margin, margin),
            CameraAnchor.TOP_RIGHT: (ww - w - margin, margin),
            CameraAnchor.BOTTOM_LEFT: (margin, wh - h - margin),
            CameraAnchor.BOTTOM_RIGHT: (ww - w - margin, wh - h - margin),
        }
        best_dist = float("inf")
        best_anchor = CameraAnchor.FREE
        for anchor, (cx, cy) in corners.items():
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_anchor = anchor
        return best_anchor if best_dist <= threshold else CameraAnchor.FREE

    # ── Camera public API ─────────────────────────────────────────

    def set_camera_mode(self, mode) -> None:
        """Set camera presentation mode."""
        from aether.ui.camera_mode import CameraMode
        if isinstance(mode, str):
            mode = CameraMode.from_str(mode)
        if self._camera_state is None:
            return
        self._apply_camera_mode(mode)

    def toggle_camera(self) -> None:
        """Toggle camera between PIP and BACKGROUND (Zoom/Teams style)."""
        from aether.ui.camera_mode import CameraMode
        if self._camera_state is None:
            return
        if self._camera_state.mode == CameraMode.BACKGROUND:
            self.set_camera_mode(CameraMode.PIP)
        else:
            self.set_camera_mode(CameraMode.BACKGROUND)

    def show_camera(self) -> None:
        """Show camera in its current mode (default PIP)."""
        from aether.ui.camera_mode import CameraMode
        if self._camera is None:
            return
        mode = self._camera_state.mode if self._camera_state else CameraMode.PIP
        if mode == CameraMode.HIDDEN:
            mode = CameraMode.PIP
        self.set_camera_mode(mode)

    def hide_camera(self) -> None:
        """Hide camera."""
        from aether.ui.camera_mode import CameraMode
        self.set_camera_mode(CameraMode.HIDDEN)

    # ── UI-1: Runtime show / hide / toggle ───────────────────────────

    def show(self) -> None:
        """Show the shell window at runtime."""
        if self._window:
            self._window.show()

    def hide(self) -> None:
        """Hide the shell window without shutdown."""
        if self._window:
            self._window.hide()

    def toggle(self) -> None:
        """Toggle shell window visibility."""
        if self._window:
            if self._window.isVisible():
                self.hide()
            else:
                self.show()

    @property
    def is_visible(self) -> bool:
        """Query current window visibility."""
        if self._window:
            return self._window.isVisible()
        return False

    # ── Workspace ───────────────────────────────────────────────────

    def _restore_workspace(self) -> None:
        """Restore the last session layout, then announce the active layout."""
        workspace_manager = self._context.workspace_manager
        if workspace_manager is None or self._workspace_scene is None:
            return

        self._workspace_scene.bind_workspace_manager(workspace_manager)

        restored = None
        try:
            restored = workspace_manager.last_layout_sessions()
        except Exception:
            logger.exception("Failed to read last layout sessions")

        if restored:
            try:
                self._workspace_scene.apply_sessions(restored)
            except Exception:
                logger.exception("Failed to apply restored sessions")
        elif not workspace_manager.restore_last():
            try:
                workspace_manager.load_workspace("hand")
            except Exception:
                logger.exception("Failed to load default workspace")

        # Announce the active layout (StatusBar subscribes to this)
        if self._context.event_bus is not None:
            try:
                from aether.core.event_bus_v2 import Event
                from aether.core.event_type import EventType
                self._context.event_bus.publish(Event(
                    type=EventType.WORKSPACE_LOADED,
                    payload={"name": workspace_manager.current_layout},
                    source=self.__class__.__name__,
                ))
            except Exception:
                logger.debug("Failed to publish workspace.loaded event")

    # ── Shell chrome (Status Bar + Notifications) ─────────────────

    def _create_statusbar(self) -> None:
        from aether.ui.status_bar_widget import StatusBarWidget

        status_bar = StatusBarWidget(self._window)
        status_bar.bind_context(self._context)
        self._status_bar = status_bar

    def _create_notifications(self) -> None:
        from aether.ui.notification_widget import NotificationWidget
        from aether.ui.status_bar_widget import StatusBarWidget

        notifications = NotificationWidget(self._window)
        config = self._context.config
        if config:
            sb_cfg = config.get("gui.status_bar") or {}
            nt_cfg = config.get("gui.notifications") or {}
            bar_height = int(sb_cfg.get("height", StatusBarWidget.STATUS_HEIGHT))
            notifications.configure(
                max_visible=int(nt_cfg.get("max_visible", 3)),
                dismiss_ms=int(nt_cfg.get("auto_dismiss_ms", 4000)),
                position=nt_cfg.get("position", "bottom_right"),
                spacing=int(nt_cfg.get("spacing", 8)),
                status_bar_height=bar_height,
            )
        notifications.bind_context(self._context)
        self._notification_widget = notifications

    def _layout_shell(self) -> None:
        """Pin the status bar to the bottom; reflow toasts; reposition camera."""
        if self._window is None:
            return
        if self._status_bar is not None:
            bar_h = self._status_bar.height()
            self._status_bar.setGeometry(
                0, self._window.height() - bar_h, self._window.width(), bar_h
            )
        if self._notification_widget is not None:
            self._notification_widget.reposition()
        # Reposition backdrop, scrim, and camera on resize
        if self._backdrop is not None:
            self._backdrop.setGeometry(0, 0, self._window.width(), self._window.height())
        if self._scrim is not None:
            self._scrim.setGeometry(0, 0, self._window.width(), self._window.height())
        if self._camera is not None and self._camera_state is not None:
            from aether.ui.camera_mode import CameraMode
            if self._camera_state.mode in (CameraMode.PIP, CameraMode.MINIMAL):
                self._apply_pip_geometry(self._camera_state.width, self._camera_state.height)

    # ── Command palette ───────────────────────────────────────────

    def _create_palette(self) -> None:
        from aether.ui.command_palette_widget import CommandPaletteWidget

        palette = CommandPaletteWidget(self._window)
        palette.bind_context(self._context)
        palette_x = (self._window.width() - palette.width()) // 2
        palette.move(palette_x, 60)
        self._palette = palette

    def _wire_palette(self) -> None:
        """Rebuild palette entries now that the workspace manager is active."""
        if self._palette is None:
            return
        try:
            self._palette.refresh()
            logger.info("Command palette wired")
        except Exception:
            logger.exception("Failed to refresh command palette")

    # ── Events (resize + hotkeys) ─────────────────────────────────

    def _install_event_filter(self) -> None:
        from PySide6.QtCore import QObject

        class _EventFilter(QObject):
            def __init__(self, shell: "UIShell"):
                super().__init__()
                self._shell = shell

            def eventFilter(self, obj, event) -> bool:
                return self._shell.eventFilter(obj, event)

        self._event_filter = _EventFilter(self)
        self._window.installEventFilter(self._event_filter)

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent, Qt
        if event.type() == QEvent.Resize:
            self._layout_shell()
            return False
        if event.type() == QEvent.KeyPress:
            key = event.key()
            mods = event.modifiers()
            # Ctrl+Space or Ctrl+K → toggle command palette
            if mods & Qt.ControlModifier and (key == Qt.Key_Space or key == Qt.Key_K):
                if self._palette is not None:
                    self._palette.toggle()
                return True
            # F3 → toggle camera
            if key == Qt.Key_F3:
                self.toggle_camera()
                return True
            # Ctrl+Shift+1..4 → camera modes
            if mods & (Qt.ControlModifier | Qt.ShiftModifier):
                from aether.ui.camera_mode import CameraMode
                if key == Qt.Key_1:
                    self.set_camera_mode(CameraMode.BACKGROUND); return True
                if key == Qt.Key_2:
                    self.set_camera_mode(CameraMode.PIP); return True
                if key == Qt.Key_3:
                    self.set_camera_mode(CameraMode.MINIMAL); return True
                if key == Qt.Key_4:
                    self.set_camera_mode(CameraMode.HIDDEN); return True
            if key == Qt.Key_F1 and self._timeline:
                vis = not self._timeline.isVisible()
                self._timeline.setVisible(vis)
                if self._context.hud_manager:
                    self._context.hud_manager.add_widget(self._timeline, layer=3)
                return True
            if key == Qt.Key_F2 and self._perf_hud:
                self._perf_hud.setVisible(not self._perf_hud.isVisible())
                return True
        return False

    # ── Headless dashboard ────────────────────────────────────────

    def _build_headless_dashboard(self, show_window: bool = True) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

        window = QWidget()
        window.setWindowTitle("Aether Dashboard")
        window.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        window.setAttribute(Qt.WA_TranslucentBackground)
        window.resize(400, 500)

        frame_layout = QVBoxLayout(window)
        frame_layout.setContentsMargins(12, 12, 12, 12)

        hdr = QLabel("AETHER")
        hdr.setFont(QFont("Consolas", 11, QFont.Bold))
        hdr.setStyleSheet("color:#00ffff;")
        frame_layout.addWidget(hdr)

        self._window = window
        if show_window:
            window.show()
        logger.info("Headless dashboard created (visible=%s)", show_window)
