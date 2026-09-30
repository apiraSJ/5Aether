"""CameraWidget — renders camera feed via FrameBroker.

Dumb view: polls FrameBroker at 30fps, renders as scaled QLabel.

Signals:
    moved(int, int)     — emitted on mouse-release after drag
    double_clicked()    — emitted on double-click

All visual presentation (rounded corners, shadow, PiP style) is applied
externally by UIShell — this widget stays mode-agnostic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel

if TYPE_CHECKING:
    from aether.phase_d.hand_plugin import FrameBroker

logger = logging.getLogger("Aether.CameraWidget")


class CameraWidget(QLabel):
    """Camera feed widget — dumb view, mode-agnostic."""

    moved = Signal(int, int)
    double_clicked = Signal()

    def __init__(self, broker: FrameBroker, parent=None) -> None:
        super().__init__(parent)
        self._broker = broker
        self._visible = True
        self._drag_enabled = False
        self._dragging = False
        self._drag_start = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(160, 90)
        self.setStyleSheet("background:transparent;")
        self.setMouseTracking(True)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_frame)
        self._timer.start(33)  # ~30fps

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start(33)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._timer.stop()

    def _poll_frame(self) -> None:
        """Grab latest frame from broker and render."""
        if not self.isVisible():
            return  # Do not convert/render frames while hidden

        frame = self._broker.get_frame() if self._broker else None
        if frame is None:
            return

        import cv2

        h, w, ch = frame.shape
        bytes_per_line = ch * w
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        q_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_image)
        scaled = pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(scaled)

    # ── Drag ──────────────────────────────────────────────────────

    def set_drag_enabled(self, enabled: bool) -> None:
        self._drag_enabled = enabled

    def mousePressEvent(self, event) -> None:
        if self._drag_enabled and event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and self._drag_start is not None:
            delta = event.position() - self._drag_start
            new_pos = self.pos() + delta.toPoint()
            self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.LeftButton:
            self._dragging = False
            self._drag_start = None
            self.moved.emit(self.x(), self.y())
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    # ── Public API ────────────────────────────────────────────────

    def toggle(self) -> None:
        self.set_visible(not self._visible)

    def stop(self) -> None:
        self._timer.stop()

    # ── HUD Protocol (no-ops — Qt drives painting) ────────────────

    def update(self) -> None:
        pass

    def paint(self) -> None:
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
