"""StatusWidget — top bar HUD: REC, AETHER, FPS, Camera, Tracking, AI status.

Reads from OverlayModel.scene — no EventBus subscription.
Conforms to HUDManager Widget Protocol: update() + paint().

Optimized: caches values, only sets text/styles when data changes.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

if TYPE_CHECKING:
    from aether.ui.overlay_model import OverlayModel

WHITE = QColor(255, 255, 255)
GRAY = QColor(191, 197, 210)
ACCENT = QColor(96, 165, 250)


class StatusWidget(QWidget):
    """Top bar showing system status. Pure renderer from model.

    Optimized: only updates QLabel text/styles when data actually changes.
    """

    def __init__(self, model: OverlayModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._boot_time = time.time()
        # Cached state to avoid redundant setText/setStyleSheet
        self._prev_fps = -1.0
        self._prev_camera = None
        self._prev_tracking = None
        self._prev_ai = None
        self._prev_uptime_secs = -1
        self._visible = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(16)

        light = QFont("Segoe UI Variable", 9, QFont.Light)

        self._rec = QLabel("● REC")
        self._rec.setFont(light)
        self._rec.setStyleSheet("color:#FF4444;")

        self._title = QLabel("AETHER")
        self._title.setFont(QFont("Segoe UI Variable", 10, QFont.Medium))
        self._title.setStyleSheet("color:white;")

        self._fps = QLabel("-- FPS")
        self._fps.setFont(light)
        self._fps.setStyleSheet("color:#BFC5D2;")

        self._camera = QLabel("Camera: --")
        self._camera.setFont(light)
        self._camera.setStyleSheet("color:#BFC5D2;")

        self._tracking = QLabel("Tracking: --")
        self._tracking.setFont(light)
        self._tracking.setStyleSheet("color:#BFC5D2;")

        self._ai = QLabel("AI: --")
        self._ai.setFont(light)
        self._ai.setStyleSheet("color:#BFC5D2;")

        self._uptime = QLabel("00:00:00")
        self._uptime.setFont(light)
        self._uptime.setStyleSheet("color:#BFC5D2;")

        layout.addWidget(self._rec)
        layout.addWidget(self._title)
        layout.addStretch()
        layout.addWidget(self._fps)
        layout.addWidget(self._camera)
        layout.addWidget(self._tracking)
        layout.addWidget(self._ai)
        layout.addWidget(self._uptime)

    def update(self) -> None:
        scene = self._model.scene

        # FPS — only update if changed by >= 1
        fps_int = int(scene.fps)
        if fps_int != self._prev_fps:
            self._fps.setText(f"{scene.fps:.0f} FPS")
            self._prev_fps = fps_int

        # Camera — only update if state changed
        if scene.camera_active != self._prev_camera:
            cam_color = "#60A5FA" if scene.camera_active else "#BFC5D2"
            self._camera.setText(f"Camera: {'ON' if scene.camera_active else 'OFF'}")
            self._camera.setStyleSheet(f"color:{cam_color};")
            self._prev_camera = scene.camera_active

        # Tracking — only update if state changed
        if scene.tracking != self._prev_tracking:
            track_color = "#60A5FA" if scene.tracking else "#F59E0B"
            self._tracking.setText(f"Tracking: {'ON' if scene.tracking else 'OFF'}")
            self._tracking.setStyleSheet(f"color:{track_color};")
            self._prev_tracking = scene.tracking

        # AI — only update if state changed
        if scene.ai_ready != self._prev_ai:
            ai_color = "#60A5FA" if scene.ai_ready else "#BFC5D2"
            self._ai.setText(f"AI: {'Ready' if scene.ai_ready else 'Standby'}")
            self._ai.setStyleSheet(f"color:{ai_color};")
            self._prev_ai = scene.ai_ready

        # Uptime — only update every second
        secs = int(time.time() - self._boot_time)
        if secs != self._prev_uptime_secs:
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            self._uptime.setText(f"{h:02d}:{m:02d}:{s:02d}")
            self._prev_uptime_secs = secs

        # Only schedule repaint if anything changed
        # (Qt coalesces update() calls anyway, but we skip the cost above)

    def paint(self) -> None:
        pass

    def is_visible(self) -> bool:
        """Check if widget is visible."""
        return self._visible and super().isVisible()

    def get_dirty_rect(self) -> tuple[float, float, float, float] | None:
        """No partial repaint for status widget."""
        return None
