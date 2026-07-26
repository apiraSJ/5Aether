"""GUIPlugin — lightweight HUD orchestrator.

Creates OverlayModel, OverlayController, HUDManager, and assembles vision HUD widgets.
In headless mode, falls back to a simple dashboard.

Architecture:
    EventBus → OverlayController → OverlayModel → Widgets → HUDManager → Screen
    GUIPlugin only creates widgets, registers them with HUDManager, and drives the render loop.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import TYPE_CHECKING, Optional

from aether.core.plugin import TickablePlugin, PluginMetadata
from aether.core.service_container import ServiceContainer

if TYPE_CHECKING:
    pass

logger = logging.getLogger("Aether.GUIPlugin")


class GUIPlugin(TickablePlugin):
    """HUD orchestrator. Creates widgets, registers with HUDManager, drives render loop."""

    name = "gui_plugin"

    def __init__(self) -> None:
        self._container: Optional[ServiceContainer] = None
        self._event_bus = None
        self._command_bus = None
        self._app = None
        self._window = None
        self._overlay_model = None
        self._overlay_controller = None
        self._hud_manager = None
        self._timeline = None
        self._perf_hud = None
        self._running = False
        self._boot_time = time.time()
        self._is_vision_mode = False

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="GUI", version="2.0", category="ui",
            description="Vision HUD overlay with EventBus-driven state"
        )

    def eventFilter(self, obj, event) -> bool:
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == 0x01000030 and self._timeline:  # Qt.Key_F1
                vis = not self._timeline.isVisible()
                self._timeline.setVisible(vis)
                if self._hud_manager:
                    layer = 3 if vis else 3
                    self._hud_manager.add_widget(self._timeline, layer=layer)
                return True
            if key == 0x01000031 and self._perf_hud:  # Qt.Key_F2
                self._perf_hud.setVisible(not self._perf_hud.isVisible())
                return True
        return False

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._command_bus = container.resolve("command_bus")
        self._event_bus = container.resolve("event_bus")

        # Detect vision mode from config
        config = container.resolve("config") if container.has("config") else None
        if config:
            self._is_vision_mode = config.get("app.mode", "") == "vision"

        # Create overlay model
        from aether.ui.overlay_model import OverlayModel
        self._overlay_model = OverlayModel()

        # Create overlay controller (subscribes to EventBus)
        from aether.ui.overlay_controller import OverlayController
        self._overlay_controller = OverlayController(self._event_bus, self._overlay_model)

        # Create HUD manager
        from aether.ui.hud_manager import HUDManager
        self._hud_manager = HUDManager()

        logger.info("GUIPlugin initialized (vision=%s)", self._is_vision_mode)

    def start(self) -> None:
        try:
            from PySide6.QtWidgets import QApplication
            self._app = QApplication.instance() or QApplication(sys.argv)
            self._app.setQuitOnLastWindowClosed(False)

            if self._is_vision_mode:
                self._create_vision_hud()
            else:
                self._create_headless_dashboard()

            self._running = True
            logger.info("GUIPlugin UI started")
        except ImportError:
            logger.warning("PySide6 not available, running headless")
            self._running = True
        except Exception as e:
            logger.exception("GUIPlugin start failed: %s", e)

    # ── Vision Mode HUD ─────────────────────────────────────────────

    def _create_vision_hud(self) -> None:
        from PySide6.QtCore import Qt, QObject, QEvent
        from PySide6.QtWidgets import QWidget, QStackedLayout

        class _EventFilter(QObject):
            def __init__(self, plugin):
                super().__init__()
                self._plugin = plugin
            def eventFilter(self, obj, event):
                return self._plugin.eventFilter(obj, event)

        window = QWidget()
        window.setWindowTitle("Aether Vision HUD")
        window.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        window.setAttribute(Qt.WA_TranslucentBackground)
        window.resize(640, 480)

        layout = QStackedLayout(window)
        layout.setStackingMode(QStackedLayout.StackAll)

        # Camera feed (background — layer 0)
        broker = None
        if self._container and self._container.has("frame_broker"):
            broker = self._container.resolve("frame_broker")

        if broker:
            from aether.ui.camera_widget import CameraWidget
            cam = CameraWidget(broker)
            layout.addWidget(cam)
            self._hud_manager.add_widget(cam, layer=0)

        # Overlay (transparent, paints on top — layer 1)
        from aether.ui.overlay_widget import OverlayWidget
        overlay = OverlayWidget(self._overlay_model)
        layout.addWidget(overlay)
        self._hud_manager.add_widget(overlay, layer=1)

        # Status bar (top — layer 2)
        from aether.ui.status_widget import StatusWidget
        status = StatusWidget(self._overlay_model, window)
        status.setGeometry(0, 0, 640, 28)
        self._hud_manager.add_widget(status, layer=2)

        # Object list (left side — layer 2)
        from aether.ui.object_list_widget import ObjectListWidget
        obj_list = ObjectListWidget(self._overlay_model, window)
        obj_list.setGeometry(0, 28, 160, 400)
        self._hud_manager.add_widget(obj_list, layer=2)

        # Gesture bar (bottom — layer 2)
        from aether.ui.gesture_widget import GestureWidget
        gesture = GestureWidget(self._overlay_model, window)
        gesture.setGeometry(0, 448, 640, 32)
        self._hud_manager.add_widget(gesture, layer=2)

        # Timeline (hidden, toggle with key — layer 3)
        from aether.ui.timeline_widget import TimelineWidget
        timeline = TimelineWidget(self._overlay_model, window)
        timeline.setGeometry(480, 28, 160, 400)
        timeline.hide()
        self._hud_manager.add_widget(timeline, layer=3)
        self._timeline = timeline

        # Performance HUD (developer mode, hidden by default — layer 3)
        from aether.ui.performance_hud import PerformanceHUD
        perf_hud = PerformanceHUD(window)
        perf_hud.setGeometry(0, 460, 220, 120)
        self._hud_manager.add_widget(perf_hud, layer=3)
        self._perf_hud = perf_hud

        # Position top-right of screen
        screen = self._app.primaryScreen().geometry()
        window.move(screen.width() - 660, 20)

        self._window = window
        self._event_filter = _EventFilter(self)
        window.installEventFilter(self._event_filter)
        window.show()

        logger.info("Vision HUD created (%d widgets, %d layers)",
                     self._hud_manager.widget_count, len(self._hud_manager.layers))

    # ── Headless Dashboard ──────────────────────────────────────────

    def _create_headless_dashboard(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QListWidget
        from PySide6.QtGui import QFont

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

        self._objects_list = QListWidget()
        self._objects_list.setStyleSheet(
            "QListWidget{background:rgba(0,0,0,0.3);border:1px solid rgba(0,255,255,0.2);"
            "border-radius:6px;color:#e0e0e0;font-family:Consolas;font-size:10px;}"
        )
        frame_layout.addWidget(self._objects_list, 1)

        self._toast_label = QLabel("")
        self._toast_label.setAlignment(Qt.AlignCenter)
        self._toast_label.setStyleSheet(
            "QLabel{background:rgba(0,200,100,0.9);color:white;border-radius:6px;padding:6px;"
            "font-family:Consolas;font-size:10px;}"
        )
        self._toast_label.hide()
        frame_layout.addWidget(self._toast_label)

        self._window = window
        window.show()

    # ── Command Input ───────────────────────────────────────────────

    def _send_command(self, text: str) -> None:
        from aether.core.command import Command
        parts = text.split()
        if not parts:
            return
        cmd, args = parts[0].lower(), parts[1:]

        if cmd == "remember" and len(args) >= 2:
            data = {}
            for a in args[1:]:
                if "=" in a:
                    k, v = a.split("=", 1)
                    try:
                        data[k] = float(v) if "." in v else int(v)
                    except ValueError:
                        data[k] = v
            self._command_bus.dispatch(Command(
                name="memory.remember", source="gui",
                params={"object_id": args[0], "data": data}
            ))
        elif cmd == "recall" and args:
            self._command_bus.dispatch(Command(
                name="memory.recall", source="gui", params={"object_id": args[0]}
            ))
        elif cmd == "forget" and args:
            self._command_bus.dispatch(Command(
                name="memory.forget", source="gui", params={"object_id": args[0]}
            ))

    # ── Toast ───────────────────────────────────────────────────────

    def _show_toast(self, msg: str, level: str = "ok") -> None:
        if not hasattr(self, '_toast_label') or not self._toast_label:
            return
        colors = {
            "ok": "rgba(0,200,100,0.9)", "error": "rgba(220,50,50,0.9)",
            "warning": "rgba(220,180,0,0.9)", "info": "rgba(0,150,255,0.9)"
        }
        self._toast_label.setStyleSheet(
            f"QLabel{{background:{colors.get(level, colors['ok'])};color:white;"
            f"border-radius:6px;padding:6px;font-family:Consolas;font-size:10px;}}"
        )
        self._toast_label.setText(msg)
        self._toast_label.show()

        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, self._toast_label.hide)

    # ── Lifecycle ───────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        if self._app and self._running:
            # Drive HUD render pipeline — throttled by HUDManager per layer
            if self._hud_manager:
                self._hud_manager.update()
                self._hud_manager.paint()
            self._app.processEvents()

    def stop(self) -> None:
        self._running = False
        if self._overlay_controller:
            self._overlay_controller.unsubscribe()
        if self._hud_manager:
            self._hud_manager.clear()
        if self._window:
            self._window.hide()

    def shutdown(self) -> None:
        self.stop()
        logger.info("GUIPlugin shutdown")
