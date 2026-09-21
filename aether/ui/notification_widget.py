"""NotificationWidget — floating toast stack for Aether.

Subscribes ONLY to EventType.NOTIFICATION_CREATED (produced by
NotificationManager). Never touches notification internals or panel
services. Clicking a toast dispatches its `action` command on the
CommandBus (ui.* namespace) — the widget knows only the command name.

Stacking: bottom-right, above the StatusBar. At most `max_visible`
toasts (FIFO eviction). Auto-dismiss after `dismiss_ms`; toasts with
duration <= 0 (e.g. errors) stay until dismissed by the user.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QTimer, Qt, QEvent
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from aether.core.command import Command
from aether.core.event_type import EventType
from aether.ui.ui_context import UIContext

logger = logging.getLogger("Aether.NotificationWidget")

FONT = QFont("Segoe UI Variable", 8)
TOAST_WIDTH = 320
TOAST_HEIGHT = 40

LEVEL_STYLES = {
    "info": ("#3b82f6", "ℹ"),
    "success": ("#22c55e", "✓"),
    "warning": ("#eab308", "⚠"),
    "error": ("#ef4444", "✕"),
}


class _ToastFrame(QFrame):
    """A single clickable toast."""

    def __init__(self, payload: Dict[str, Any], parent: QWidget) -> None:
        super().__init__(parent)
        self._payload = payload
        self._command_bus = None
        self._action = payload.get("action")

        level = payload.get("level") or payload.get("type") or "info"
        color, icon = LEVEL_STYLES.get(level, LEVEL_STYLES["info"])

        self.setFixedSize(TOAST_WIDTH, TOAST_HEIGHT)
        self.setStyleSheet(
            f"QFrame{{background: rgba(24, 27, 40, 245); border: 1px solid {color};"
            f"border-left: 4px solid {color}; border-radius: 6px;}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        icon_label.setFont(QFont("Segoe UI Variable", 10))
        layout.addWidget(icon_label)

        text_label = QLabel(str(payload.get("text", "")))
        text_label.setStyleSheet("color: #e8ecf5; border: none; background: transparent;")
        text_label.setFont(FONT)
        text_label.setWordWrap(True)
        layout.addWidget(text_label, 1)

        self.setToolTip(str(payload.get("text", "")))

    def bind(self, command_bus: Any) -> None:
        self._command_bus = command_bus

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self._activate()

    def _activate(self) -> None:
        action = self._action or {}
        command_name = action.get("command")
        if command_name and self._command_bus is not None:
            try:
                self._command_bus.dispatch(Command(
                    name=command_name,
                    source="notification",
                    params=dict(action.get("params") or {}),
                ))
            except Exception:
                logger.exception("Failed to dispatch notification action %s", command_name)


class NotificationWidget(QWidget):
    """Container that manages the visible toast stack."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._event_bus = None
        self._command_bus = None
        self._toasts: List[_ToastFrame] = []

        self._max_visible = 3
        self._dismiss_ms = 4000
        self._position = "bottom_right"
        self._spacing = 8
        self._status_bar_height = 28
        self._margin = 10

        self.setObjectName("NotificationWidget")
        self.setStyleSheet("QWidget#NotificationWidget{background: transparent;}")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hide()

    # ── Configuration ──────────────────────────────────────────────

    def configure(self, *, max_visible: int = 3, dismiss_ms: int = 4000,
                  position: str = "bottom_right", spacing: int = 8,
                  status_bar_height: int = 28) -> None:
        self._max_visible = max_visible
        self._dismiss_ms = dismiss_ms
        self._position = position
        self._spacing = spacing
        self._status_bar_height = status_bar_height

    # ── Service wiring ─────────────────────────────────────────────

    def wire_services(self, command_bus: Any, event_bus: Any) -> None:
        """Backward-compatible alias for bind_context()."""
        self.bind_context(UIContext(command_bus=command_bus, event_bus=event_bus))

    def bind_context(self, context: UIContext) -> None:
        """Subscribe to notification.created only."""
        self._command_bus = context.command_bus
        self._event_bus = context.event_bus
        if context.event_bus is None:
            return
        try:
            context.event_bus.subscribe(EventType.NOTIFICATION_CREATED, self._on_notification)
        except Exception:
            pass

    def unwire(self) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.unsubscribe(EventType.NOTIFICATION_CREATED, self._on_notification)
            except Exception:
                pass
        self._event_bus = None

    # ── Event handling ─────────────────────────────────────────────

    def _on_notification(self, event) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        self.add_notification(payload)

    def add_notification(self, payload: Dict[str, Any]) -> None:
        """Add a toast from a notification payload dict."""
        if self._max_visible <= 0:
            return
        while len(self._toasts) >= self._max_visible:
            oldest = self._toasts.pop(0)
            oldest.deleteLater()

        toast = _ToastFrame(payload, self)
        toast.bind(self._command_bus)
        toast.show()
        self._toasts.append(toast)

        duration = payload.get("duration")
        if duration is None or duration > 0:
            QTimer.singleShot(self._dismiss_ms, lambda t=toast: self._dismiss(t))

        self._reflow()

    def _dismiss(self, toast: _ToastFrame) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        toast.deleteLater()
        self._reflow()

    def clear(self) -> int:
        count = len(self._toasts)
        for toast in self._toasts:
            toast.deleteLater()
        self._toasts.clear()
        self._reflow()
        return count

    @property
    def toast_count(self) -> int:
        return len(self._toasts)

    # ── Layout ─────────────────────────────────────────────────────

    def reposition(self) -> None:
        """Reposition the whole stack relative to the parent window."""
        parent = self.parentWidget()
        if parent is None:
            return
        self._reflow()

    def _reflow(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        if not self._toasts:
            self.resize(0, 0)
            self.hide()
            return

        count = len(self._toasts)
        total_height = count * TOAST_HEIGHT + (count - 1) * self._spacing
        stack_width = TOAST_WIDTH
        stack_height = total_height

        if self._position == "bottom_right":
            x = parent.width() - stack_width - self._margin
            y = parent.height() - self._status_bar_height - stack_height - self._margin
        elif self._position == "top_right":
            x = parent.width() - stack_width - self._margin
            y = self._margin
        else:  # top_left fallback
            x = self._margin
            y = self._margin

        x = max(0, x)
        y = max(0, y)

        self.setGeometry(x, y, stack_width, stack_height)
        for i, toast in enumerate(self._toasts):
            toast.move(0, i * (TOAST_HEIGHT + self._spacing))
        self.show()
