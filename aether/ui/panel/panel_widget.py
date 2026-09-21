"""PanelWidget — base QWidget for all workspace panels.

Composition: wraps a panel model (AbstractPanel subclass).
Frame styling (background, title bar, border, resize handles)
is drawn with QPainter. Content area is a real QWidget filled
by subclasses.

Geometry, visibility, and focus are synced by PanelRegistry
— this widget NEVER initiates layout changes. Mouse events
are forwarded to InteractionController via signals.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QPainterPath, QMouseEvent,
)
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from aether.ui.panel.i_panel_widget import IPanelWidget

logger = logging.getLogger("Aether.PanelWidget")

TITLE_BAR_HEIGHT = 28
PANEL_RADIUS = 8
RESIZE_HANDLE_SIZE = 12
FOCUS_RING_COLOR = QColor(96, 165, 250, 220)
FOCUS_RING_GLOW = QColor(96, 165, 250, 40)
FOCUS_RING_WIDTH = 2.0
FOCUS_RING_GLOW_WIDTH = 6

PANEL_BG = QColor(15, 17, 26, 200)
PANEL_TITLE_BG = QColor(25, 30, 45, 220)
PANEL_BORDER = QColor(60, 65, 85, 160)
PANEL_BORDER_HOVER = QColor(96, 165, 250, 140)
PANEL_BORDER_SELECTED = QColor(96, 165, 250, 220)
PANEL_TEXT = QColor(200, 210, 230, 220)

FONT_TITLE = QFont("Segoe UI Variable", 10, QFont.Light)


class TitleBarWidget(QWidget):
    """Panel title bar — label + Pin/Min/Max/Close buttons."""

    # Signals for window operations
    pin_clicked = Signal()
    min_clicked = Signal()
    max_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, label: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self.setMouseTracking(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 4, 0)
        layout.setSpacing(4)

        # Label
        self._label = QLabel(label)
        self._label.setStyleSheet("color: rgba(200, 210, 230, 220); font-size: 10px;")
        layout.addWidget(self._label)
        layout.addStretch()

        # Window buttons
        btn_style = (
            "QPushButton{background:transparent;border:none;color:rgba(200,210,230,180);"
            "font-size:12px;padding:2px 6px;border-radius:3px;}"
            "QPushButton:hover{background:rgba(255,255,255,10);}"
        )

        self._pin_btn = QPushButton("\u25CF")  # ●
        self._pin_btn.setFixedSize(20, 20)
        self._pin_btn.setStyleSheet(btn_style)
        self._pin_btn.setToolTip("Pin to top")
        self._pin_btn.clicked.connect(self.pin_clicked.emit)
        layout.addWidget(self._pin_btn)

        self._min_btn = QPushButton("\u2014")  # —
        self._min_btn.setFixedSize(20, 20)
        self._min_btn.setStyleSheet(btn_style)
        self._min_btn.setToolTip("Minimize")
        self._min_btn.clicked.connect(self.min_clicked.emit)
        layout.addWidget(self._min_btn)

        self._max_btn = QPushButton("\u25A1")  # □
        self._max_btn.setFixedSize(20, 20)
        self._max_btn.setStyleSheet(btn_style)
        self._max_btn.setToolTip("Maximize")
        self._max_btn.clicked.connect(self.max_clicked.emit)
        layout.addWidget(self._max_btn)

        self._close_btn = QPushButton("\u2715")  # ✕
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.setStyleSheet(
            btn_style.replace("color:rgba(200,210,230,180)", "color:rgba(255,100,100,180)")
        )
        self._close_btn.setToolTip("Close")
        self._close_btn.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self._close_btn)

    def set_label(self, text: str) -> None:
        self._label.setText(text)

    def set_pinned(self, pinned: bool) -> None:
        self._pin_btn.setStyleSheet(
            self._pin_btn.styleSheet().replace(
                "color:rgba(255,165,0,220)" if pinned else "color:rgba(200,210,230,180)",
                "color:rgba(255,165,0,220)" if not pinned else "color:rgba(200,210,230,180)"
            )
        )


class PanelWidget(QWidget, IPanelWidget):
    """Base widget for workspace panels.

    Subclasses override _build_content() to add their widgets
    to the content layout.
    """

    # Signals for InteractionController
    mouse_pressed = Signal(str, int, int, str)  # panel_id, x, y, region
    mouse_dragged = Signal(str, int, int)
    mouse_released = Signal(str, int, int)

    # Signals for WorkspaceScene (window ops + geometry auto-save)
    window_op = Signal(str, str)  # (panel_id, pin|minimize|maximize|close)
    geometry_changed = Signal(str, int, int, int, int)  # (panel_id, x, y, w, h)

    def __init__(
        self,
        panel_id: str,
        panel_type: str,
        label: str,
        parent=None,
    ) -> None:
        QWidget.__init__(self, parent)
        self._panel_id = panel_id
        self._panel_type = panel_type
        self._label = label
        self._has_focus = False
        self._mounted = False
        self._state = "idle"  # idle, hovered, selected, dragging, resizing

        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setMouseTracking(True)

        # Layout
        self._outer_layout = QVBoxLayout(self)
        self._outer_layout.setContentsMargins(0, 0, 0, 0)
        self._outer_layout.setSpacing(0)

        # Title bar
        self._title_bar = TitleBarWidget(label)
        self._title_bar.pin_clicked.connect(self._on_pin)
        self._title_bar.min_clicked.connect(self._on_minimize)
        self._title_bar.max_clicked.connect(self._on_maximize)
        self._title_bar.close_clicked.connect(self._on_close)
        self._outer_layout.addWidget(self._title_bar)

        # Content container — subclasses fill via _build_content()
        self._content = QWidget()
        self._content.setAttribute(Qt.WA_TranslucentBackground)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(8, 4, 8, 8)
        self._content_layout.setSpacing(4)
        self._outer_layout.addWidget(self._content, 1)

        self._build_content()

    # ── Subclass hook ───────────────────────────────────────────────

    def _build_content(self) -> None:
        """Override in subclass to add content widgets."""
        pass

    def _on_mount(self) -> None:
        """Override in subclass for mount-time setup (e.g. connect signals)."""
        pass

    def _on_unmount(self) -> None:
        """Override in subclass for cleanup on unmount."""
        pass

    # ── IPanelWidget ────────────────────────────────────────────────

    @property
    def panel_id(self) -> str:
        return self._panel_id

    @property
    def panel_type(self) -> str:
        return self._panel_type

    def mount(self) -> None:
        self._mounted = True
        self._on_mount()
        logger.debug("Panel '%s' mounted", self._panel_id)

    def unmount(self) -> None:
        self._mounted = False
        self._on_unmount()
        logger.debug("Panel '%s' unmounted", self._panel_id)

    def destroy(self) -> None:
        self.unmount()
        self.deleteLater()

    def focus_widget(self) -> None:
        self._has_focus = True
        self.raise_()
        self._state = "selected"
        self.update()

    def blur_widget(self) -> None:
        self._has_focus = False
        self._state = "idle"
        self.update()

    def has_focus(self) -> bool:
        return self._has_focus

    def set_geometry(self, x: int, y: int, w: int, h: int) -> None:
        self.setGeometry(x, y, w, h)

    def geometry(self) -> tuple[int, int, int, int]:
        g = super().geometry()
        return (g.x(), g.y(), g.width(), g.height())

    def update_content(self) -> None:
        """Refresh panel from data model. Override in subclass."""
        pass

    def serialize(self) -> dict:
        return {"panel_id": self._panel_id, "panel_type": self._panel_type}

    def restore(self, state: dict) -> None:
        pass

    # ── State ──────────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """Set interaction state: idle, hovered, selected, dragging, resizing."""
        self._state = state
        self.update()

    # ── Window operations (called by TitleBarWidget buttons) ────────

    def _on_pin(self) -> None:
        """Toggle pin state."""
        self._pinned = not getattr(self, '_pinned', False)
        self._title_bar.set_pinned(self._pinned)
        self.window_op.emit(self._panel_id, "pin")

    def _on_minimize(self) -> None:
        """Minimize panel."""
        self.hide()
        self.window_op.emit(self._panel_id, "minimize")

    def _on_maximize(self) -> None:
        """Maximize panel (fill parent)."""
        parent = self.parentWidget()
        if parent:
            self.setGeometry(0, 0, parent.width(), parent.height())
        self.window_op.emit(self._panel_id, "maximize")

    def _on_close(self) -> None:
        """Close panel (hide)."""
        self.hide()
        self.window_op.emit(self._panel_id, "close")

    def set_pinned_state(self, pinned: bool) -> None:
        """Set pinned state from outside (restore, controller)."""
        self._pinned = bool(pinned)
        self._title_bar.set_pinned(self._pinned)

    def is_pinned(self) -> bool:
        return bool(getattr(self, "_pinned", False))

    def is_visible(self) -> bool:
        return self.isVisible()

    # ── Geometry change tracking (for auto-save) ─────────────────────

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.geometry_changed.emit(
            self._panel_id, self.x(), self.y(), self.width(), self.height(),
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.geometry_changed.emit(
            self._panel_id, self.x(), self.y(), self.width(), self.height(),
        )


    # ── Hit regions ─────────────────────────────────────────────────

    def _hit_region(self, x: int, y: int) -> str:
        """Determine what region was clicked: title, content, resize, border."""
        w, h = self.width(), self.height()
        if x >= w - RESIZE_HANDLE_SIZE - 4 and y >= h - RESIZE_HANDLE_SIZE - 4:
            return "resize"
        if y <= TITLE_BAR_HEIGHT:
            return "title"
        return "content"

    # ── Mouse events → signals (InteractionController handles) ──────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        region = self._hit_region(int(event.position().x()), int(event.position().y()))
        self.mouse_pressed.emit(self._panel_id, int(event.position().x()), int(event.position().y()), region)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.mouse_dragged.emit(self._panel_id, int(event.position().x()), int(event.position().y()))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.mouse_released.emit(self._panel_id, int(event.position().x()), int(event.position().y()))
        event.accept()

    # ── Frame rendering ─────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        bg = QColor(PANEL_BG)
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, w, h, PANEL_RADIUS, PANEL_RADIUS)
        painter.save()
        painter.setClipPath(clip)

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(0, 0, w, h, PANEL_RADIUS, PANEL_RADIUS)

        # Title bar
        tw = TITLE_BAR_HEIGHT
        painter.setBrush(PANEL_TITLE_BG)
        painter.drawRect(0, 0, w, tw)

        painter.restore()

        # Border
        if self._state == "hovered":
            border_color = PANEL_BORDER_HOVER
            border_width = 2.0
        elif self._state in ("selected", "focused"):
            border_color = PANEL_BORDER_SELECTED
            border_width = 2.0
        elif self._state == "dragging":
            border_color = QColor(96, 165, 250, 180)
            border_width = 2.0
        elif self._state == "resizing":
            border_color = QColor(96, 165, 250, 180)
            border_width = 2.0
        else:
            border_color = PANEL_BORDER
            border_width = 1.5

        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0, 0, w, h, PANEL_RADIUS, PANEL_RADIUS)

        # Focus ring (glow + border)
        if self._has_focus:
            # Glow
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(FOCUS_RING_GLOW))
            painter.drawRoundedRect(
                -FOCUS_RING_GLOW_WIDTH, -FOCUS_RING_GLOW_WIDTH,
                w + FOCUS_RING_GLOW_WIDTH * 2, h + FOCUS_RING_GLOW_WIDTH * 2,
                PANEL_RADIUS + 4, PANEL_RADIUS + 4,
            )
            # Focus border
            painter.setPen(QPen(FOCUS_RING_COLOR, FOCUS_RING_WIDTH))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(-1, -1, w + 2, h + 2, PANEL_RADIUS, PANEL_RADIUS)

        # Resize handle
        if self._state in ("selected", "focused", "idle"):
            hx = w - RESIZE_HANDLE_SIZE
            hy = h - RESIZE_HANDLE_SIZE
            painter.setPen(QPen(QColor(255, 255, 255, 150), 1.0))
            painter.drawLine(hx + 2, h - 2, w - 2, hy + 2)
            painter.drawLine(hx + 5, h - 2, w - 2, hy + 5)
            painter.drawLine(hx + 8, h - 2, w - 2, hy + 8)

        painter.end()
