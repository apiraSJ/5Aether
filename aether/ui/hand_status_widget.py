"""HandStatusWidget — displays hand tracking status in the HUD.

Shows:
    - Hand detected (yes/no)
    - Current gesture
    - Confidence
    - Interaction mode

Reads from OverlayModel.interaction_status — no EventBus subscription.
Conforms to HUDManager Widget Protocol: update() + paint().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from aether.ui.overlay_model import OverlayModel

WHITE = QColor(255, 255, 255)
GRAY = QColor(191, 197, 210)
ACCENT = QColor(96, 165, 250)
GREEN = QColor(74, 222, 128)
RED = QColor(248, 113, 113)

FONT_TITLE = QFont("Segoe UI Variable", 10, QFont.DemiBold)
FONT_LABEL = QFont("Segoe UI Variable", 9, QFont.Light)
FONT_VALUE = QFont("Segoe UI Variable", 9, QFont.Normal)


class HandStatusWidget(QWidget):
    """Hand status display widget. Reads from OverlayModel.

    Data flow:
        OverlayModel.interaction_status → update() → paintEvent()
    """

    def __init__(self, model: OverlayModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._visible = True
        self._hand_detected = False
        self._gesture = "None"
        self._confidence = 0.0
        self._mode = "IDLE"
        self._state = "IDLE"

        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedSize(160, 100)

    def update(self) -> None:
        """Read interaction status from model."""
        status = self._model.interaction_status
        self._state = status.state
        self._mode = status.cursor_mode
        self._gesture = status.action or "Idle"
        self._hand_detected = status.target_panel != "" or self._state != "IDLE"
        self._confidence = 0.95 if self._hand_detected else 0.0
        super().update()

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

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 6, 6)

        y = 16
        painter.setFont(FONT_TITLE)
        painter.setPen(WHITE)
        painter.drawText(10, y, "HAND STATUS")
        y += 20

        # Detected
        painter.setFont(FONT_LABEL)
        painter.setPen(GRAY)
        painter.drawText(10, y, "Detected:")
        painter.setFont(FONT_VALUE)
        painter.setPen(GREEN if self._hand_detected else RED)
        painter.drawText(80, y, "YES" if self._hand_detected else "NO")
        y += 16

        # Gesture
        painter.setFont(FONT_LABEL)
        painter.setPen(GRAY)
        painter.drawText(10, y, "Gesture:")
        painter.setFont(FONT_VALUE)
        painter.setPen(WHITE)
        painter.drawText(80, y, self._gesture)
        y += 16

        # Confidence
        painter.setFont(FONT_LABEL)
        painter.setPen(GRAY)
        painter.drawText(10, y, "Confidence:")
        painter.setFont(FONT_VALUE)
        painter.setPen(ACCENT)
        painter.drawText(80, y, f"{self._confidence:.0%}")
        y += 16

        # Mode
        painter.setFont(FONT_LABEL)
        painter.setPen(GRAY)
        painter.drawText(10, y, "Mode:")
        painter.setFont(FONT_VALUE)
        painter.setPen(ACCENT)
        painter.drawText(80, y, self._mode)

        painter.end()
