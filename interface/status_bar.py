"""
Status Bar — Minimal top-right overlay

Compact widget in top-right corner, ~10-15% of screen.
Shows HP, player name, time/date in a tight, beautiful layout.
"""

import time
import logging
from datetime import datetime
from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QRadialGradient,
    QLinearGradient, QPainterPath,
)


logger = logging.getLogger("Aether.StatusBar")

# ─── Theme ────────────────────────────────────────────────────────
BG_COLOR = QColor(240, 240, 240, 210)
BG_BORDER = QColor(200, 200, 200, 120)
HP_NORMAL = QColor(0, 255, 136)
HP_HURT = QColor(255, 204, 0)
HP_CRITICAL = QColor(255, 51, 48)
HP_BG = QColor(40, 40, 50, 120)
ACCENT = QColor(255, 119, 0)
TEXT_DARK = QColor(40, 40, 40)
TEXT_MID = QColor(100, 100, 100)
TEXT_LIGHT = QColor(160, 160, 160)


class StatusBar(QWidget):
    """Compact top-right status panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._visible = False
        self._hp = 85
        self._hp_max = 100
        self._player_name = "Aether"
        self._cpu_pct = 0.0
        self._mem_pct = 0.0

        self._setup_window()
        self._start_clock()

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
            g = screen.geometry()
            pw = int(g.width() * 0.20)
            ph = int(g.height() * 0.14)
            self.setGeometry(g.x() + g.width() - pw - 16, g.y() + 16, pw, ph)
        else:
            self.setGeometry(1920 - 384, 16, 384, 150)

    def _start_clock(self):
        self._timer = QTimer()
        self._timer.timeout.connect(self.update)
        self._timer.start(1000)

    # ─── Public API ───────────────────────────────────────────────

    def show_bar(self):
        self._visible = True
        self.show()
        self.update()

    def hide_bar(self):
        self._visible = False
        self.hide()

    def update_stats(self, hp: int = None, hp_max: int = None,
                     player_name: str = None, cpu_pct: float = None,
                     mem_pct: float = None):
        if hp is not None:
            self._hp = hp
        if hp_max is not None:
            self._hp_max = hp_max
        if player_name is not None:
            self._player_name = player_name
        if cpu_pct is not None:
            self._cpu_pct = cpu_pct
        if mem_pct is not None:
            self._mem_pct = mem_pct
        self.update()

    @property
    def is_visible(self):
        return self._visible

    # ─── Painting ─────────────────────────────────────────────────

    def paintEvent(self, event):
        if not self._visible:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        h = self.height()
        pad = 14

        # ── Background card ──
        card = QRectF(0, 0, w, h)
        path = QPainterPath()
        path.addRoundedRect(card, 14, 14)
        painter.setClipPath(path)

        bg = QLinearGradient(card.topLeft(), card.bottomRight())
        bg.setColorAt(0, QColor(250, 250, 250, 225))
        bg.setColorAt(1, QColor(240, 240, 240, 210))
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(BG_BORDER, 1))
        painter.drawRoundedRect(card, 14, 14)
        painter.setClipping(False)

        y = pad

        # ── Player name ──
        name_font = QFont("Segoe UI", 18, QFont.Bold)
        painter.setFont(name_font)
        painter.setPen(QPen(TEXT_DARK))
        painter.drawText(QRectF(pad, y, w - pad * 2, 28), Qt.AlignLeft, self._player_name)
        y += 32

        # ── Orange accent line ──
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(ACCENT))
        painter.drawRoundedRect(QRectF(pad, y, 50, 3), 1, 1)
        y += 14

        # ── HP bar ──
        hp_font = QFont("Segoe UI", 14, QFont.Bold)
        hp_label_font = QFont("Segoe UI", 12)
        bar_w = w - pad * 2 - 70
        bar_h = 18
        bar_x = pad
        bar_y = y

        ratio = max(0.0, min(1.0, self._hp / max(self._hp_max, 1)))
        hp_color = HP_NORMAL if ratio > 0.6 else (HP_HURT if ratio > 0.3 else HP_CRITICAL)

        # Bar background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(HP_BG))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 4, 4)

        # Bar fill
        fill_w = bar_w * ratio
        if fill_w > 2:
            fill = QRectF(bar_x, bar_y, fill_w, bar_h)
            fp = QPainterPath()
            fp.addRoundedRect(fill, 4, 4)
            painter.setClipPath(fp)
            painter.setBrush(QBrush(hp_color))
            painter.setPen(Qt.NoPen)
            painter.drawRect(fill)
            painter.setClipping(False)

        # HP text on bar
        painter.setFont(hp_font)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(QRectF(bar_x + 8, bar_y, bar_w, bar_h), Qt.AlignVCenter, f"{self._hp}")

        # HP label right
        painter.setFont(hp_label_font)
        painter.setPen(QPen(TEXT_MID))
        painter.drawText(QRectF(bar_x + bar_w + 8, bar_y, 60, bar_h), Qt.AlignVCenter, f"/ {self._hp_max}")
        y += bar_h + 14

        # ── Stats row ──
        stat_font = QFont("Segoe UI", 11)
        painter.setFont(stat_font)
        painter.setPen(QPen(TEXT_MID))

        now = datetime.now()
        time_str = now.strftime("%H:%M")
        date_str = now.strftime("%m/%d")
        cpu_str = f"CPU {self._cpu_pct:.0f}%"

        stats = f"{cpu_str}    {time_str}  {date_str}"
        painter.drawText(QRectF(pad, y, w - pad * 2, 20), Qt.AlignLeft, stats)
        y += 20

        painter.end()
