"""
Cursor Overlay — Transparent PySide6 fullscreen window

Draws the Aether virtual cursor (blue holographic reticle).
Cursor only moves during Pointing_Up gesture.
On other gestures, cursor floats frozen at last position.
"""

import math
import logging
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QRadialGradient, QBrush, QFont

from core.cursor_manager import CursorManager


class CursorOverlay(QWidget):
    """Transparent fullscreen overlay that draws the virtual cursor."""

    def __init__(self, cursor_manager: CursorManager, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("Aether.CursorOverlay")
        self.cursor_manager = cursor_manager

        # Reticle appearance
        self._outer_radius = 24
        self._inner_radius = 4
        self._ring_width = 2.5
        self._glow_radius = 44

        # Colors
        self._color_idle = QColor(0, 200, 255, 180)       # cyan — frozen/pointing idle
        self._color_moving = QColor(0, 255, 200, 220)      # green-cyan — cursor moving
        self._color_pinch = QColor(0, 255, 180, 240)       # bright green — pinch/click
        self._color_grab = QColor(255, 200, 0, 220)        # gold — grab
        self._color_no_hand = QColor(80, 80, 100, 60)      # dim — no hand

        # Animation
        self._pulse_phase = 0.0
        self._pulse_speed = 3.0

        # State
        self._gesture_label = ""

        self._setup_window()
        self._start_render_loop()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.NoDropShadowWindowHint |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        else:
            self.setGeometry(0, 0, 1920, 1080)

    def _start_render_loop(self):
        self._render_timer = QTimer()
        self._render_timer.timeout.connect(self.update)
        self._render_timer.start(16)  # ~60 FPS

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        state = self.cursor_manager.get_state()

        if not state.visible:
            painter.end()
            return

        x, y = state.x, state.y
        if x == 0 and y == 0:
            painter.end()
            return

        # Pulse animation
        self._pulse_phase += self._pulse_speed / 60.0
        pulse = 0.85 + 0.15 * math.sin(self._pulse_phase)

        # Choose color based on state
        if state.is_grab:
            color = self._color_grab
        elif state.is_pinch:
            color = self._color_pinch
        elif state.moving:
            color = self._color_moving
        else:
            color = self._color_idle  # frozen / other gesture

        # Glow
        glow = QRadialGradient(QPointF(x, y), self._glow_radius * pulse)
        glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 45))
        glow.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), 12))
        glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(x, y), self._glow_radius * pulse, self._glow_radius * pulse)

        # Outer ring
        outer = self._outer_radius * pulse
        painter.setPen(QPen(color, self._ring_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(x, y), outer, outer)

        # Inner dot
        inner_color = QColor(color)
        inner_color.setAlpha(255)
        painter.setBrush(QBrush(inner_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(x, y), self._inner_radius, self._inner_radius)

        # Crosshair ticks
        line_color = QColor(color)
        line_color.setAlpha(70)
        painter.setPen(QPen(line_color, 1.0))
        tick = 8
        painter.drawLine(QPointF(x - outer - 4, y), QPointF(x - outer + tick, y))
        painter.drawLine(QPointF(x + outer - tick, y), QPointF(x + outer + 4, y))
        painter.drawLine(QPointF(x, y - outer - 4), QPointF(x, y - outer + tick))
        painter.drawLine(QPointF(x, y + outer - tick), QPointF(x, y + outer + 4))

        # Gesture label below cursor
        if state.gesture and state.gesture != "Unknown":
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            label_color = QColor(color)
            label_color.setAlpha(160)
            painter.setPen(QPen(label_color))
            label = state.gesture.replace("_", " ")
            if not state.moving:
                label += "  · frozen"
            painter.drawText(QPointF(x + outer + 8, y + 4), label)

        painter.end()
