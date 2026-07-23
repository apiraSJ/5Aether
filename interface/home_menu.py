"""
Home Menu — Vertical Chain Layout with Sub-panels

Opens on Open_Palm gesture. Vertical chain of items stacked below cursor.
Sub-panels slide out from right side on hover.
Modern minimal UI with smooth transitions.

Color palette:
  Background: rgba(240, 240, 240, 0.85)
  Idle ring:  #C0C0C0 (silver)
  Hover:      #FF7700 (orange)
  Text:       #333333 / #888888
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, Callable, List
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QPointF, QRectF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont,
    QLinearGradient, QPainterPath,
)


logger = logging.getLogger("Aether.HomeMenu")

# ─── Theme ────────────────────────────────────────────────────────
BG_COLOR = QColor(240, 240, 240, 217)
BG_BORDER = QColor(200, 200, 200, 120)
IDLE_RING = QColor(192, 192, 192, 180)
HOVER_RING = QColor(255, 119, 0, 255)
HOVER_GLOW = QColor(255, 119, 0, 40)
HOVER_BG = QColor(255, 119, 0, 30)
TEXT_PRIMARY = QColor(51, 51, 51)
TEXT_SECONDARY = QColor(136, 136, 136)
TEXT_HOVER = QColor(255, 255, 255)
LINE_COLOR = QColor(192, 192, 192, 60)
SUBPANEL_BG = QColor(248, 248, 248, 240)
SUBPANEL_BORDER = QColor(220, 220, 220, 180)
SUBPANEL_ITEM_HOVER = QColor(255, 119, 0, 25)
SUBPANEL_ACCENT = QColor(255, 119, 0, 200)
BRIDGE_COLOR = QColor(255, 119, 0, 15)

# ─── Layout ────────────────────────────────────────────────────────
ITEM_W = 140
ITEM_H = 48
ICON_SIZE = 28
CHAIN_GAP = 8
SUBPANEL_W = 200
SUBPANEL_PAD = 12
SUBPANEL_ITEM_H = 34
SUBPANEL_GAP = 4              # minimal gap between item and sub-panel
PANEL_SLIDE_SPEED = 0.22      # smooth but fast


@dataclass
class SubMenuItem:
    label: str
    action: str


@dataclass
class MenuItem:
    label: str
    icon: str
    action: str
    sub_items: List[SubMenuItem] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    hover: bool = False


MENU_ITEMS = [
    MenuItem("Memory", "🧠", "open_memory", [
        SubMenuItem("Recent", "memory_recent"),
        SubMenuItem("Search", "memory_search"),
        SubMenuItem("Categories", "memory_categories"),
    ]),
    MenuItem("Tasks", "📋", "open_tasks", [
        SubMenuItem("Active", "tasks_active"),
        SubMenuItem("History", "tasks_history"),
        SubMenuItem("New Task", "tasks_new"),
    ]),
    MenuItem("Settings", "⚙️", "open_settings", [
        SubMenuItem("Display", "settings_display"),
        SubMenuItem("Audio", "settings_audio"),
        SubMenuItem("Debug", "settings_debug"),
    ]),
    MenuItem("Camera", "📷", "open_camera", [
        SubMenuItem("Snapshot", "camera_snapshot"),
        SubMenuItem("Record", "camera_record"),
        SubMenuItem("Filters", "camera_filters"),
    ]),
    MenuItem("Help", "❓", "open_help", [
        SubMenuItem("Gestures", "help_gestures"),
        SubMenuItem("Commands", "help_commands"),
        SubMenuItem("About", "help_about"),
    ]),
    MenuItem("Exit", "🚪", "close_ui", []),
]


class HomeMenu(QWidget):
    """Vertical chain menu with sub-panels, clamped to screen."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._visible = False
        self._cursor_x = 0.0
        self._cursor_y = 0.0
        self._hover_index = -1
        self._hover_sub_index = -1
        self._on_select: Optional[Callable] = None

        # Animation
        self._subpanel_alpha = 0.0
        self._subpanel_target = 0.0
        self._hovered_item_with_subs = -1

        # Fonts
        self._icon_font = QFont("Segoe UI Emoji", 18)
        self._label_font = QFont("Segoe UI", 12, QFont.DemiBold)
        self._sub_font = QFont("Segoe UI", 11)
        self._sub_title_font = QFont("Segoe UI", 10, QFont.Bold)

        self._setup_window()

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

    # ─── Public API ───────────────────────────────────────────────

    def show_at(self, x: float, y: float, on_select: Callable = None):
        self._cursor_x = x
        self._cursor_y = y
        self._on_select = on_select
        self._visible = True
        self._hover_index = -1
        self._hover_sub_index = -1
        self._subpanel_alpha = 0.0
        self._subpanel_target = 0.0
        self._hovered_item_with_subs = -1
        self._compute_positions()
        self.show()
        self.update()

    def hide_menu(self):
        self._visible = False
        self._hover_index = -1
        self._hover_sub_index = -1
        self._subpanel_alpha = 0.0
        self._subpanel_target = 0.0
        self._hovered_item_with_subs = -1
        self.hide()

    @property
    def is_visible(self):
        return self._visible

    @property
    def hovered_action(self) -> Optional[str]:
        if self._hover_sub_index >= 0 and self._hover_index >= 0:
            item = MENU_ITEMS[self._hover_index]
            if self._hover_sub_index < len(item.sub_items):
                return item.sub_items[self._hover_sub_index].action
        if 0 <= self._hover_index < len(MENU_ITEMS):
            return MENU_ITEMS[self._hover_index].action
        return None

    # ─── Position Calculation (vertical chain) ────────────────────

    def _compute_positions(self):
        """Place items in a vertical chain below the cursor, clamped to screen."""
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.geometry()
            sw, sh = g.width(), g.height()
        else:
            sw, sh = 1920, 1080

        n = len(MENU_ITEMS)
        total_h = n * ITEM_H + (n - 1) * CHAIN_GAP

        start_x = self._cursor_x
        start_y = self._cursor_y + 24

        if start_y + total_h > sh - 20:
            start_y = sh - 20 - total_h
        if start_y < 20:
            start_y = 20

        if start_x + ITEM_W > sw - 20:
            start_x = sw - 20 - ITEM_W
        if start_x < 20:
            start_x = 20

        for i, item in enumerate(MENU_ITEMS):
            item.x = start_x
            item.y = start_y + i * (ITEM_H + CHAIN_GAP)
            item.hover = False

    def _get_item_rect(self, idx: int) -> QRectF:
        item = MENU_ITEMS[idx]
        return QRectF(item.x, item.y, ITEM_W, ITEM_H)

    def _get_subpanel_rect(self, item_index: int) -> QRectF:
        item = MENU_ITEMS[item_index]
        screen = QApplication.primaryScreen()
        sw = screen.geometry().width() if screen else 1920

        x = item.x + ITEM_W + SUBPANEL_GAP
        y = item.y - 4
        h = SUBPANEL_PAD * 2 + len(item.sub_items) * SUBPANEL_ITEM_H + 28

        if x + SUBPANEL_W > sw - 20:
            x = item.x - SUBPANEL_GAP - SUBPANEL_W

        return QRectF(x, y, SUBPANEL_W, h)

    def _get_bridge_rect(self, item_index: int) -> QRectF:
        """Hit area between main item and sub-panel to prevent hover gaps."""
        item = MENU_ITEMS[item_index]
        sub_rect = self._get_subpanel_rect(item_index)

        if sub_rect.x() > item.x + ITEM_W:
            # Sub-panel to the right
            return QRectF(
                item.x + ITEM_W, item.y - 4,
                SUBPANEL_GAP + 8, ITEM_H + 8,
            )
        else:
            # Sub-panel to the left
            return QRectF(
                sub_rect.right() - 8, item.y - 4,
                SUBPANEL_GAP + 8, ITEM_H + 8,
            )

    # ─── Hover Detection ──────────────────────────────────────────

    def update_hover(self, cursor_x: float, cursor_y: float):
        if not self._visible:
            return None

        old_hover = self._hover_index
        old_sub = self._hover_sub_index
        self._hover_index = -1
        self._hover_sub_index = -1
        pt = QPointF(cursor_x, cursor_y)

        # 1. Check sub-panel first (if open) — highest priority
        if old_hover >= 0 and self._subpanel_alpha > 0.3:
            sub_rect = self._get_subpanel_rect(old_hover)
            if sub_rect.contains(pt):
                self._hover_index = old_hover
                local_y = cursor_y - sub_rect.y() - SUBPANEL_PAD - 28
                sub_idx = int(local_y / SUBPANEL_ITEM_H)
                if 0 <= sub_idx < len(MENU_ITEMS[old_hover].sub_items):
                    self._hover_sub_index = sub_idx

        # 2. Check bridge area (gap between item and sub-panel)
        if self._hover_index < 0 and old_hover >= 0 and self._subpanel_alpha > 0.3:
            bridge = self._get_bridge_rect(old_hover)
            if bridge.contains(pt):
                self._hover_index = old_hover

        # 3. Check main items
        if self._hover_index < 0:
            for i, item in enumerate(MENU_ITEMS):
                rect = self._get_item_rect(i)
                if rect.contains(pt):
                    self._hover_index = i
                    break

        # 4. Check bridge areas for ALL items with sub-panels (not just current)
        if self._hover_index < 0:
            for i, item in enumerate(MENU_ITEMS):
                if not item.sub_items:
                    continue
                bridge = self._get_bridge_rect(i)
                if bridge.contains(pt):
                    self._hover_index = i
                    break

        for i, item in enumerate(MENU_ITEMS):
            item.hover = (i == self._hover_index)

        # Sub-panel visibility — keep open if hovering item OR sub-panel
        if self._hover_index >= 0 and len(MENU_ITEMS[self._hover_index].sub_items) > 0:
            self._subpanel_target = 1.0
            self._hovered_item_with_subs = self._hover_index
        elif self._hover_sub_index >= 0:
            # Still on a sub-item — keep open
            pass
        else:
            self._subpanel_target = 0.0

        if self._hover_index != old_hover or self._hover_sub_index != old_sub:
            self.update()

        if self._hover_sub_index >= 0 and self._hover_index >= 0:
            return MENU_ITEMS[self._hover_index].sub_items[self._hover_sub_index].action
        if 0 <= self._hover_index < len(MENU_ITEMS):
            return MENU_ITEMS[self._hover_index].action
        return None

    def select_hovered(self) -> Optional[str]:
        # Sub-panel item selected
        if self._hover_sub_index >= 0 and self._hover_index >= 0:
            item = MENU_ITEMS[self._hover_index]
            if self._hover_sub_index < len(item.sub_items):
                action = item.sub_items[self._hover_sub_index].action
                logger.info(f"Menu sub-select: {action}")
                if self._on_select:
                    self._on_select(action)
                self.hide_menu()
                return action

        # Main item
        if 0 <= self._hover_index < len(MENU_ITEMS):
            item = MENU_ITEMS[self._hover_index]
            if not item.sub_items:
                action = item.action
                logger.info(f"Menu select: {action}")
                if self._on_select:
                    self._on_select(action)
                self.hide_menu()
                return action
            else:
                # Expand sub-panel on first click (keep open)
                self._subpanel_target = 1.0
                self._hovered_item_with_subs = self._hover_index
                self.update()
                return None

        return None

    # ─── Painting ─────────────────────────────────────────────────

    def paintEvent(self, event):
        if not self._visible:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Animate sub-panel
        self._subpanel_alpha += (self._subpanel_target - self._subpanel_alpha) * PANEL_SLIDE_SPEED
        if abs(self._subpanel_alpha - self._subpanel_target) < 0.01:
            self._subpanel_alpha = self._subpanel_target

        self._draw_chain(painter)
        self._draw_items(painter)

        if self._subpanel_alpha > 0.01 and self._hovered_item_with_subs >= 0:
            self._draw_subpanel(painter, self._hovered_item_with_subs)

        painter.end()

        if abs(self._subpanel_alpha - self._subpanel_target) > 0.01:
            self.update()

    def _draw_chain(self, painter: QPainter):
        """Draw vertical chain connectors between items."""
        painter.setPen(QPen(LINE_COLOR, 1.5))
        for i in range(len(MENU_ITEMS) - 1):
            y1 = MENU_ITEMS[i].y + ITEM_H
            y2 = MENU_ITEMS[i + 1].y
            x = MENU_ITEMS[i].x + ITEM_W / 2
            painter.drawLine(QPointF(x, y1), QPointF(x, y2))

        # Line from cursor to first item
        if MENU_ITEMS:
            first = MENU_ITEMS[0]
            painter.drawLine(
                QPointF(self._cursor_x, self._cursor_y),
                QPointF(first.x + ITEM_W / 2, first.y),
            )

    def _draw_items(self, painter: QPainter):
        for i, item in enumerate(MENU_ITEMS):
            is_hovered = (i == self._hover_index)
            x, y = item.x, item.y

            rect = QRectF(x, y, ITEM_W, ITEM_H)

            if is_hovered:
                # Glow
                glow = QLinearGradient(QPointF(x, y), QPointF(x + ITEM_W, y + ITEM_H))
                glow.setColorAt(0, QColor(255, 119, 0, 40))
                glow.setColorAt(1, QColor(255, 119, 0, 10))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawRoundedRect(rect.adjusted(-6, -6, 6, 6), 14, 14)

                painter.setBrush(QBrush(HOVER_BG))
                painter.setPen(QPen(HOVER_RING, 2.5))
            else:
                painter.setBrush(QBrush(BG_COLOR))
                painter.setPen(QPen(IDLE_RING, 1.5))

            painter.drawRoundedRect(rect, 12, 12)

            # Icon circle
            icon_r = ICON_SIZE / 2
            icon_cx = x + 18
            icon_cy = y + ITEM_H / 2

            if is_hovered:
                painter.setBrush(QBrush(HOVER_RING))
                painter.setPen(Qt.NoPen)
            else:
                painter.setBrush(QBrush(QColor(220, 220, 220, 180)))
                painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(icon_cx, icon_cy), icon_r, icon_r)

            # Icon emoji
            painter.setFont(self._icon_font)
            painter.setPen(QPen(TEXT_HOVER if is_hovered else TEXT_PRIMARY))
            painter.drawText(
                QRectF(icon_cx - 12, icon_cy - 12, 24, 24),
                Qt.AlignCenter, item.icon,
            )

            # Label
            painter.setFont(self._label_font)
            painter.setPen(QPen(TEXT_HOVER if is_hovered else TEXT_PRIMARY))
            painter.drawText(
                QRectF(x + 36, y, ITEM_W - 40, ITEM_H),
                Qt.AlignVCenter | Qt.AlignLeft, item.label,
            )

            # Arrow indicator for items with sub-items
            if item.sub_items:
                is_expanded = (i == self._hovered_item_with_subs and self._subpanel_alpha > 0.3)
                ax = x + ITEM_W - 14
                ay = y + ITEM_H / 2
                color = HOVER_RING if is_hovered else TEXT_SECONDARY
                painter.setPen(QPen(color, 1.5))
                if is_expanded:
                    # Down arrow when expanded
                    painter.drawLine(QPointF(ax - 4, ay - 2), QPointF(ax, ay + 2))
                    painter.drawLine(QPointF(ax, ay + 2), QPointF(ax + 4, ay - 2))
                else:
                    # Right arrow when collapsed
                    painter.drawLine(QPointF(ax - 3, ay - 3), QPointF(ax + 1, ay))
                    painter.drawLine(QPointF(ax + 1, ay), QPointF(ax - 3, ay + 3))

    def _draw_subpanel(self, painter: QPainter, item_index: int):
        item = MENU_ITEMS[item_index]
        if not item.sub_items:
            return

        rect = self._get_subpanel_rect(item_index)
        slide_offset = (1.0 - self._subpanel_alpha) * rect.width()
        dr = QRectF(rect.x() + slide_offset, rect.y(), rect.width(), rect.height())

        # Background with subtle shadow
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(dr.adjusted(2, 2, 2, 2), 10, 10)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 20 * self._subpanel_alpha)))
        painter.drawRoundedRect(dr.adjusted(2, 2, 2, 2), 10, 10)

        path = QPainterPath()
        path.addRoundedRect(dr, 10, 10)
        painter.setClipPath(path)

        bg = QLinearGradient(dr.topLeft(), dr.bottomRight())
        bg.setColorAt(0, SUBPANEL_BG)
        bg.setColorAt(1, QColor(245, 245, 245, 230))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(SUBPANEL_BORDER, 1))
        painter.drawRoundedRect(dr, 10, 10)
        painter.setClipping(False)

        # Connector line from item to sub-panel
        painter.setPen(QPen(QColor(255, 119, 0, 80 * self._subpanel_alpha), 1))
        if dr.x() > item.x + ITEM_W:
            src_x = item.x + ITEM_W
            dst_x = dr.x()
        else:
            src_x = item.x
            dst_x = dr.right()
        painter.drawLine(
            QPointF(src_x, item.y + ITEM_H / 2),
            QPointF(dst_x, dr.y() + dr.height() / 2),
        )

        # Title
        painter.setFont(self._sub_title_font)
        painter.setPen(QPen(SUBPANEL_ACCENT))
        painter.drawText(
            QRectF(dr.x() + SUBPANEL_PAD, dr.y() + 6, dr.width() - SUBPANEL_PAD * 2, 20),
            Qt.AlignLeft, item.label.upper(),
        )

        # Separator
        sep_y = dr.y() + 26
        painter.setPen(QPen(QColor(220, 220, 220, 120), 1))
        painter.drawLine(
            QPointF(dr.x() + SUBPANEL_PAD, sep_y),
            QPointF(dr.right() - SUBPANEL_PAD, sep_y),
        )

        # Items
        painter.setFont(self._sub_font)
        for j, sub in enumerate(item.sub_items):
            sy = dr.y() + 32 + j * SUBPANEL_ITEM_H
            sr = QRectF(dr.x() + SUBPANEL_PAD, sy, dr.width() - SUBPANEL_PAD * 2, SUBPANEL_ITEM_H)
            is_sub = (item_index == self._hover_index and j == self._hover_sub_index)

            if is_sub:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(SUBPANEL_ITEM_HOVER))
                painter.drawRoundedRect(sr, 6, 6)
                painter.setPen(QPen(HOVER_RING))
            else:
                painter.setPen(QPen(TEXT_PRIMARY))

            painter.drawText(sr.adjusted(8, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, sub.label)

            if is_sub:
                ax = dr.right() - SUBPANEL_PAD - 4
                ay = sy + SUBPANEL_ITEM_H / 2
                painter.setPen(QPen(HOVER_RING, 2))
                painter.drawLine(QPointF(ax - 5, ay - 3), QPointF(ax, ay))
                painter.drawLine(QPointF(ax, ay), QPointF(ax - 5, ay + 3))
