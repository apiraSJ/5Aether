"""
Home Menu — Gesture-driven radial menu

Appears on Open_Palm. Navigated by cursor + pinch click.
6 buttons arranged in a semicircle around the cursor position.
"""

import math
import logging
from dataclasses import dataclass
from typing import Optional, Callable
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QFont, QRadialGradient


@dataclass
class MenuItem:
    label: str
    icon: str
    action: str
    x: float = 0.0
    y: float = 0.0
    hover: bool = False


class HomeMenu(QWidget):
    """Semicircle gesture menu rendered on transparent overlay."""

    # Menu items
    ITEMS = [
        MenuItem("Memory",   "🧠", "open_memory"),
        MenuItem("Tasks",    "📋", "open_tasks"),
        MenuItem("Settings", "⚙️",  "open_settings"),
        MenuItem("Camera",   "📷", "open_camera"),
        MenuItem("Help",     "❓", "open_help"),
        MenuItem("Exit",     "🚪", "close_ui"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = logging.getLogger("Aether.HomeMenu")
        self._visible = False
        self._cursor_x = 0.0
        self._cursor_y = 0.0
        self._radius = 140.0
        self._button_radius = 36.0
        self._hover_index = -1
        self._on_select: Optional[Callable] = None

        # Colors
        self._bg_color = QColor(15, 18, 30, 200)
        self._btn_color = QColor(30, 40, 70, 220)
        self._btn_hover = QColor(0, 180, 255, 240)
        self._btn_border = QColor(0, 200, 255, 100)
        self._text_color = QColor(255, 255, 255)
        self._icon_color = QColor(200, 220, 255)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.NoDropShadowWindowHint |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Full screen
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        else:
            self.setGeometry(0, 0, 1920, 1080)

    def show_at(self, x: float, y: float, on_select: Callable = None):
        """Show menu centered at position."""
        self._cursor_x = x
        self._cursor_y = y
        self._on_select = on_select
        self._visible = True
        self._compute_positions()
        self.show()
        self.update()

    def hide_menu(self):
        self._visible = False
        self._hover_index = -1
        self.hide()

    @property
    def is_visible(self):
        return self._visible

    @property
    def hovered_action(self) -> Optional[str]:
        if self._hover_index >= 0:
            return self.ITEMS[self._hover_index].action
        return None

    def _compute_positions(self):
        """Place buttons in a semicircle above the cursor."""
        n = len(self.ITEMS)
        # Spread from -150° to -30° (upper semicircle)
        start_angle = math.radians(210)
        end_angle = math.radians(330)
        step = (end_angle - start_angle) / max(n - 1, 1)

        for i, item in enumerate(self.ITEMS):
            angle = start_angle + i * step
            item.x = self._cursor_x + self._radius * math.cos(angle)
            item.y = self._cursor_y + self._radius * math.sin(angle)
            item.hover = False

    def update_hover(self, cursor_x: float, cursor_y: float):
        """Update which button is hovered by cursor position."""
        if not self._visible:
            return None

        old_hover = self._hover_index
        self._hover_index = -1

        for i, item in enumerate(self.ITEMS):
            dx = cursor_x - item.x
            dy = cursor_y - item.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < self._button_radius * 1.4:
                self._hover_index = i
                item.hover = True
            else:
                item.hover = False

        if self._hover_index != old_hover:
            self.update()

        if self._hover_index >= 0:
            return self.ITEMS[self._hover_index].action
        return None

    def select_hovered(self) -> Optional[str]:
        """Select the currently hovered item. Returns action name."""
        if self._hover_index >= 0:
            action = self.ITEMS[self._hover_index].action
            self.logger.info(f"Menu selected: {action}")
            if self._on_select:
                self._on_select(action)
            self.hide_menu()
            return action
        return None

    def paintEvent(self, event):
        if not self._visible:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw connecting lines from cursor to buttons
        line_color = QColor(0, 200, 255, 30)
        painter.setPen(QPen(line_color, 1))
        for item in self.ITEMS:
            painter.drawLine(
                QPointF(self._cursor_x, self._cursor_y),
                QPointF(item.x, item.y)
            )

        # Draw buttons
        font = QFont("Segoe UI", 11, QFont.Bold)
        icon_font = QFont("Segoe UI", 18)

        for i, item in enumerate(self.ITEMS):
            is_hovered = (i == self._hover_index)

            # Button background
            if is_hovered:
                # Glow effect
                glow = QRadialGradient(QPointF(item.x, item.y), self._button_radius * 1.8)
                glow.setColorAt(0, QColor(0, 180, 255, 60))
                glow.setColorAt(1, QColor(0, 180, 255, 0))
                painter.setBrush(QBrush(glow))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(QPointF(item.x, item.y), self._button_radius * 1.8, self._button_radius * 1.8)

                painter.setBrush(QBrush(self._btn_hover))
                painter.setPen(QPen(QColor(0, 220, 255), 2))
            else:
                painter.setBrush(QBrush(self._btn_color))
                painter.setPen(QPen(self._btn_border, 1))

            painter.drawEllipse(QPointF(item.x, item.y), self._button_radius, self._button_radius)

            # Icon
            painter.setFont(icon_font)
            painter.setPen(QPen(self._text_color if is_hovered else self._icon_color))
            painter.drawText(QRectF(item.x - 20, item.y - 22, 40, 30), Qt.AlignCenter, item.icon)

            # Label (below button)
            painter.setFont(font)
            painter.setPen(QPen(self._text_color if is_hovered else QColor(180, 190, 210)))
            painter.drawText(
                QRectF(item.x - 40, item.y + self._button_radius + 4, 80, 20),
                Qt.AlignCenter, item.label
            )

        painter.end()
