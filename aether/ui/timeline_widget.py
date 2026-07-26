"""TimelineWidget — developer-mode event timeline.

Shows last N events for debugging. Hidden by default.
Reads from OverlayModel.event_history — no EventBus subscription.
Conforms to HUDManager Widget Protocol: update() + paint().
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextEdit
)

if TYPE_CHECKING:
    from aether.ui.overlay_model import OverlayModel

GRAY = QColor(191, 197, 210)


class TimelineWidget(QWidget):
    """Event timeline for developer mode. Reads from OverlayModel.event_history."""

    def __init__(self, model: OverlayModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._last_index = 0
        self._visible = True
        self._setup_ui()
        self.hide()  # Hidden by default

    def _setup_ui(self) -> None:
        self.setFixedWidth(280)
        self.setStyleSheet("background:rgba(0,0,0,0.6);border-left:1px solid rgba(255,255,255,0.1);")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        header = QLabel("Event Timeline")
        header.setFont(QFont("Segoe UI Variable", 9, QFont.Medium))
        header.setStyleSheet("color:#BFC5D2;")
        layout.addWidget(header)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            "QTextEdit{background:transparent;border:none;color:#888;"
            "font-family:'Consolas',monospace;font-size:9px;}"
        )
        layout.addWidget(self._text, 1)

    def update(self) -> None:
        """Read new events from model history and append to display."""
        history = self._model.event_history
        new_events = history[self._last_index:]
        self._last_index = len(history)

        if new_events:
            for entry in new_events:
                ts = entry.get("ts", "?")
                src = entry.get("src", "?")
                etype = entry.get("type", "?")
                self._text.append(
                    f"[{ts}] <span style='color:#60A5FA'>{src}</span> → {etype}"
                )

            if self.isVisible():
                scrollbar = self._text.verticalScrollBar()
                if scrollbar:
                    scrollbar.setValue(scrollbar.maximum())

        super().update()

    def paint(self) -> None:
        """Qt handles painting via widget system."""
        pass

    def is_visible(self) -> bool:
        return self._visible and super().isVisible()

    def get_dirty_rect(self) -> tuple[float, float, float, float] | None:
        return None

    def toggle(self) -> None:
        """Toggle visibility."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
