"""CameraWidget — renders camera feed as background of the HUD overlay.

Subscribes to FrameBroker for frame data. Frame never flows through EventBus.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel

if TYPE_CHECKING:
    from aether.phase_d.hand_plugin import FrameBroker

logger = logging.getLogger("Aether.CameraWidget")


class CameraWidget(QLabel):
    """Full-viewport camera feed background.

    Polls FrameBroker at 30fps and renders as a scaled QLabel.
    Frame data never touches EventBus — only frame_id metadata does.
    """

    def __init__(self, broker: FrameBroker, parent=None) -> None:
        super().__init__(parent)
        self._broker = broker
        self._visible = True
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 240)

        # Transparent background for overlay on top
        self.setStyleSheet("background:transparent;")

        # Poll timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_frame)
        self._timer.start(33)  # ~30fps

    def _poll_frame(self) -> None:
        """Grab latest frame from broker and render."""
        frame = self._broker.get_frame() if self._broker else None
        if frame is None:
            return

        import cv2
        import numpy as np

        h, w, ch = frame.shape
        bytes_per_line = ch * w
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        q_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)

        # Scale to fit widget, keep aspect ratio
        scaled = pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

    def stop(self) -> None:
        self._timer.stop()

    def update(self) -> None:
        """CameraWidget polls FrameBroker via QTimer; this is a no-op for HUDManager."""
        pass

    def paint(self) -> None:
        """Qt handles painting via widget system."""
        pass

    def is_visible(self) -> bool:
        return self._visible and super().isVisible()

    def set_visible(self, visible: bool) -> None:
        self._visible = visible
        if not visible:
            self.hide()
        else:
            self.show()

    def get_dirty_rect(self) -> tuple[float, float, float, float] | None:
        return None
