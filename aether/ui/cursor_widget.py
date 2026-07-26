"""CursorWidget — virtual cursor visualization.

Reads from OverlayModel.cursor — no EventBus subscription.
Conforms to HUDManager Widget Protocol: update() + paint().

Visual states:
    DEFAULT  → ○ small white circle
    HOVER    → double circle with accent glow
    PINCH    → filled accent circle
    DRAG_START → indented dot
    DRAGGING → large filled accent circle
    DRAG_END → large circle with selection glow
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QBrush, QPen
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from aether.ui.overlay_model import OverlayModel, CursorState

WHITE = QColor(255, 255, 255)
ACCENT = QColor(96, 165, 250)
SELECTION_GLOW = QColor(96, 165, 250, 50)

_STATE_MAP = {
    "default": "idle",
    "hover": "hover",
    "pinch": "dragging",
    "drag_start": "drag_start",
    "dragging": "dragging",
    "drag_end": "drag_end",
}


class CursorWidget(QWidget):
    """Visual cursor widget. Reads from OverlayModel.cursor.

    Data flow:
        OverlayModel.cursor → update() → paintEvent()
    """

    def __init__(self, model: OverlayModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._cursor_x = 0.5
        self._cursor_y = 0.5
        self._visible = True

        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(64, 64)

        self._cursor_state = "idle"
        self._selection_glow = False
        self._glow_timer = QTimer(self)
        self._glow_timer.setSingleShot(True)
        self._glow_timer.timeout.connect(self._clear_selection_glow)

    def update(self) -> None:
        """Read cursor state from model."""
        cursor = self._model.cursor
        self._cursor_x = cursor.x
        self._cursor_y = cursor.y
        self._cursor_state = _STATE_MAP.get(cursor.state.value, "idle")
        self._selection_glow = cursor.selection_glow

        # Auto-clear selection glow after 1.5s
        if self._selection_glow and not self._glow_timer.isActive():
            self._glow_timer.start(1500)

        super().update()

    def paint(self) -> None:
        """Qt handles painting via paintEvent."""
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

    def _clear_selection_glow(self) -> None:
        self._selection_glow = False
        self._model.clear_selection_glow()
        super().update()

    def paintEvent(self, event) -> None:
        """Render cursor based on its state."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx = self.width() / 2
        cy = self.height() / 2

        if self._selection_glow:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(SELECTION_GLOW))
            painter.drawEllipse(cx - 20, cy - 20, 40, 40)

        painter.setPen(Qt.NoPen)

        if self._cursor_state == "hover":
            painter.setBrush(QBrush(ACCENT))
            painter.drawEllipse(cx - 12, cy - 12, 24, 24)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(WHITE, 2))
            painter.drawEllipse(cx - 10, cy - 10, 20, 20)

        elif self._cursor_state == "drag_start":
            painter.setBrush(QBrush(WHITE))
            painter.drawEllipse(cx - 10, cy - 10, 20, 20)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(ACCENT, 3))
            painter.drawPoint(cx - 6, cy - 6)

        elif self._cursor_state == "dragging":
            painter.setBrush(QBrush(ACCENT))
            painter.drawEllipse(cx - 16, cy - 16, 32, 32)

        elif self._cursor_state == "drag_end":
            painter.setBrush(QBrush(ACCENT))
            painter.drawEllipse(cx - 32, cy - 32, 64, 64)

        else:  # idle
            painter.setBrush(QBrush(WHITE))
            painter.drawEllipse(cx - 8, cy - 8, 16, 16)

        painter.end()

    def show_cursor(self, x: float, y: float, screen_w: int, screen_h: int) -> None:
        """Move the cursor widget to the correct screen position."""
        widget_x = int(x * screen_w) - (self.width() / 2)
        widget_y = int(y * screen_h) - (self.height() / 2)
        self.move(widget_x, widget_y)
