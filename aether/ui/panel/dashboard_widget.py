"""DashboardPanelWidget — pure-view Dashboard panel.

Renders the latest PerformanceSnapshot delivered via SYSTEM_METRICS events.

Layout:
    ┌──────────┬──────────┐
    │ CPU      │ MEM      │
    │ 14%      │ 62%      │
    ├──────────┼──────────┤
    │ Plugins  │ Panels   │
    │ 17       │ 5        │
    └──────────┴──────────┘
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QLabel, QVBoxLayout,
)

from aether.core.event_type import EventType
from aether.core.performance_snapshot import PerformanceSnapshot
from aether.ui.panel.panel_widget import PanelWidget
from aether.ui.ui_context import UIContext

FONT_LABEL = QFont("Segoe UI Variable", 8, QFont.Light)
FONT_VALUE = QFont("Segoe UI Variable", 18, QFont.DemiBold)
FONT_UNIT = QFont("Segoe UI Variable", 10, QFont.Light)


class _MetricCard(QWidget):
    """Single metric card with label + value."""

    def __init__(self, label: str, value: str, unit: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(self._card_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self._label_widget = QLabel(label)
        self._label_widget.setFont(FONT_LABEL)
        self._label_widget.setStyleSheet("color: rgba(140, 150, 180, 200);")
        layout.addWidget(self._label_widget)

        val_layout = QVBoxLayout()
        val_layout.setSpacing(0)

        self._value_widget = QLabel(value)
        self._value_widget.setFont(FONT_VALUE)
        self._value_widget.setStyleSheet("color: rgba(96, 165, 250, 200);")
        val_layout.addWidget(self._value_widget)

        if unit:
            self._unit_widget = QLabel(unit)
            self._unit_widget.setFont(FONT_UNIT)
            self._unit_widget.setStyleSheet("color: rgba(140, 150, 180, 160);")
            val_layout.addWidget(self._unit_widget)

        layout.addLayout(val_layout)
        layout.addStretch()

    def set_value(self, value: str) -> None:
        self._value_widget.setText(value)

    @staticmethod
    def _card_style() -> str:
        return (
            "QWidget{background:rgba(20,22,35,200);border:1px solid rgba(60,65,85,100);"
            "border-radius:6px;}"
        )


class DashboardPanelWidget(PanelWidget):
    """Dashboard panel — renders PerformanceSnapshot from SYSTEM_METRICS events."""

    def __init__(self, panel_id: str, panel_type: str, label: str, parent=None) -> None:
        self._event_bus = None
        self._cards: dict[str, _MetricCard] = {}
        super().__init__(panel_id, panel_type, label, parent)

    def _build_content(self) -> None:
        layout = self._content_layout

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        metrics = [
            ("cpu_percent", "CPU", "%"),
            ("memory_percent", "MEM", "%"),
            ("plugins", "Plugins", ""),
            ("panels", "Panels", ""),
        ]
        for i, (key, label, unit) in enumerate(metrics):
            card = _MetricCard(label, "0", unit)
            row, col = i // 2, i % 2
            grid.addWidget(card, row, col)
            self._cards[key] = card

        layout.addLayout(grid)

    def wire_services(self, command_bus: Any, event_bus: Any) -> None:
        """Backward-compatible alias for bind_context()."""
        self.bind_context(UIContext(command_bus=command_bus, event_bus=event_bus))

    def bind_context(self, context: UIContext) -> None:
        """Subscribe to SYSTEM_METRICS events."""
        self._command_bus = context.command_bus
        self._event_bus = context.event_bus
        if context.event_bus:
            try:
                context.event_bus.subscribe(EventType.SYSTEM_METRICS, self._on_metrics)
            except Exception:
                pass

    def set_data(self, snapshot: PerformanceSnapshot) -> None:
        """Render a snapshot. Pure view — no service access."""
        for key, card in self._cards.items():
            value = getattr(snapshot, key, None)
            if isinstance(value, float):
                card.set_value(f"{value:.0f}")
            elif value is not None:
                card.set_value(str(value))

    def _on_metrics(self, event) -> None:
        snapshot = event.payload
        if isinstance(snapshot, PerformanceSnapshot):
            self.set_data(snapshot)