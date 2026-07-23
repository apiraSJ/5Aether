"""
Cursor Overlay — Transparent PySide6 fullscreen window

Draws the Aether virtual cursor (orange holographic reticle).
Matches the VR-clean theme: silver idle, orange active.
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
        self._outer_radius = 22
        self._inner_radius = 3
        self._ring_width = 2.0
        self._glow_radius = 40

        # Theme colors (matches HomeMenu)
        self._color_idle = QColor(192, 192, 192, 160)       # silver — idle
        self._color_moving = QColor(255, 140, 50, 200)       # warm orange — moving
        self._color_pinch = QColor(255, 119, 0, 240)         # bright orange — click
        self._color_grab = QColor(255, 200, 0, 220)          # gold — grab

        # Animation
        self._pulse_phase = 0.0
        self._pulse_speed = 3.0

        self._setup_window()
        self._start_render_loop()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.NoDropShadowWindowHint
            | Qt.WindowTransparentForInput
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
        pulse = 0.88 + 0.12 * math.sin(self._pulse_phase)

        # Choose color based on state
        if state.is_grab:
            color = self._color_grab
        elif state.is_pinch:
            color = self._color_pinch
        elif state.moving:
            color = self._color_moving
        else:
            color = self._color_idle

        # Glow
        glow = QRadialGradient(QPointF(x, y), self._glow_radius * pulse)
        glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 40))
        glow.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), 10))
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
        tick = 7
        painter.drawLine(QPointF(x - outer - 3, y), QPointF(x - outer + tick, y))
        painter.drawLine(QPointF(x + outer - tick, y), QPointF(x + outer + 3, y))
        painter.drawLine(QPointF(x, y - outer - 3), QPointF(x, y - outer + tick))
        painter.drawLine(QPointF(x, y + outer - tick), QPointF(x, y + outer + 3))

        # Gesture label below cursor
        if state.gesture and state.gesture != "Unknown":
            font = QFont("Segoe UI", 8)
            painter.setFont(font)
            label_color = QColor(color)
            label_color.setAlpha(140)
            painter.setPen(QPen(label_color))
            label = state.gesture.replace("_", " ")
            if not state.moving:
                label += "  · idle"
            painter.drawText(QPointF(x + outer + 8, y + 4), label)

        painter.end()
