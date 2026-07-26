"""GestureWidget — bottom panel showing current gesture, phase, and confidence.

Reads from OverlayModel.gesture — no EventBus subscription.
Conforms to HUDManager Widget Protocol: update() + paint().

Optimized: caches gesture state, only updates labels when gesture changes.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from aether.ui.overlay_model import GesturePhase

if TYPE_CHECKING:
    from aether.ui.overlay_model import OverlayModel

ACCENT = QColor(96, 165, 250)
GRAY = QColor(191, 197, 210)


class GestureWidget(QWidget):
    """Bottom bar showing gesture state. Pure renderer from model.

    Optimized: caches gesture hash, only updates when data changes.
    """

    def __init__(self, model: OverlayModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._last_gesture_hash = ""
        self._visible = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setFixedHeight(32)
        self.setStyleSheet("background:transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(16)

        light = QFont("Segoe UI Variable", 9, QFont.Light)

        self._gesture_icon = QLabel("")
        self._gesture_icon.setFont(light)
        self._gesture_icon.setStyleSheet("color:white;")
        layout.addWidget(self._gesture_icon)

        self._gesture_name = QLabel("Gesture: --")
        self._gesture_name.setFont(light)
        self._gesture_name.setStyleSheet("color:#BFC5D2;")
        layout.addWidget(self._gesture_name)

        self._gesture_conf = QLabel("")
        self._gesture_conf.setFont(light)
        self._gesture_conf.setStyleSheet("color:#60A5FA;")
        layout.addWidget(self._gesture_conf)

        self._gesture_hand = QLabel("")
        self._gesture_hand.setFont(light)
        self._gesture_hand.setStyleSheet("color:#BFC5D2;")
        layout.addWidget(self._gesture_hand)

        layout.addStretch()

        self._duration = QLabel("")
        self._duration.setFont(light)
        self._duration.setStyleSheet("color:#BFC5D2;")
        layout.addWidget(self._duration)

    def update(self) -> None:
        gesture = self._model.gesture

        # Fast hash: skip if nothing changed (name+phase+confidence rounded)
        g_hash = f"{gesture.name}:{gesture.phase.value}:{gesture.confidence:.1f}:{gesture.duration:.1f}"
        if g_hash == self._last_gesture_hash:
            return
        self._last_gesture_hash = g_hash

        if gesture.phase == GesturePhase.NONE:
            self._gesture_icon.setText("")
            self._gesture_name.setText("Gesture: --")
            self._gesture_conf.setText("")
            self._gesture_hand.setText("")
            self._duration.setText("")
            return

        icons = {
            "Open_Palm": "✋",
            "Closed_Fist": "✊",
            "Pointing_Up": "☝",
            "Thumb_Up": "👍",
            "Thumb_Down": "👎",
            "Victory": "✌",
            "ILoveYou": "🤟",
        }
        icon = icons.get(gesture.name, "🤚")
        self._gesture_icon.setText(icon)

        name = gesture.name.replace("_", " ").title()
        phase_label = gesture.phase.value.upper()
        self._gesture_name.setText(f"Gesture: {name} ({phase_label})")

        self._gesture_conf.setText(f"{gesture.confidence * 100:.0f}%")
        self._gesture_hand.setText(gesture.hand)

        if gesture.phase == GesturePhase.HOLDING:
            self._duration.setText(f"{gesture.duration:.1f}s")
        else:
            self._duration.setText("")

    def paint(self) -> None:
        pass

    def is_visible(self) -> bool:
        return self._visible and super().isVisible()

    def get_dirty_rect(self) -> tuple[float, float, float, float] | None:
        return None
