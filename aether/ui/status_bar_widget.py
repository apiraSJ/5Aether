"""StatusBarWidget — Aether shell status bar.

Shell UI: a plain QWidget pinned to the bottom of the main window.
It is NOT a PanelWidget and NOT managed by HUDManager — it renders
system status at a fixed height without per-frame repaint.

Data flow (pure view, no DI lookups):
    PerformancePlugin → SYSTEM_METRICS → StatusBarWidget.set_data(snapshot)
    WorkspaceManager  → WORKSPACE_LOADED / LAYOUT_LOADED → layout label
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from aether.core.event_type import EventType
from aether.core.performance_snapshot import PerformanceSnapshot
from aether.ui.ui_context import UIContext

STATUS_HEIGHT = 28
FONT = QFont("Segoe UI Variable", 8)
FONT_MUTED = QFont("Segoe UI Variable", 8, QFont.Light)

BG_STYLE = "background: rgba(16, 18, 30, 235); border-top: 1px solid rgba(60, 65, 85, 140);"
TEXT_STYLE = "color: rgba(190, 200, 225, 235);"
MUTED_STYLE = "color: rgba(140, 150, 180, 200);"
ACCENT_STYLE = "color: rgba(96, 165, 250, 235);"

INDICATOR_COLORS = {
    "ready": "#22c55e",
    "degraded": "#eab308",
    "offline": "#ef4444",
    "inactive": "rgba(90, 100, 130, 160)",
}

INDICATOR_LABELS = [
    ("camera_ready", "CAM"),
    ("vision_ready", "VIS"),
    ("memory_ready", "MEM"),
    ("ai_ready", "AI"),
    ("voice_ready", "VOI"),
]


class StatusBarWidget(QWidget):
    """Bottom status bar rendering SYSTEM_METRICS snapshots."""

    STATUS_HEIGHT = STATUS_HEIGHT

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._event_bus = None
        self._metrics: dict[str, QLabel] = {}
        self._metric_labels = {
            "camera_fps": "CAM",
            "hand_fps": "HAND",
            "memory_percent": "MEM",
            "cpu_percent": "CPU",
        }
        self._indicators: dict[str, QLabel] = {}
        self._layout_label: Optional[QLabel] = None

        self.setObjectName("StatusBarWidget")
        self.setFixedHeight(self.STATUS_HEIGHT)
        self.setStyleSheet(f"QWidget#StatusBarWidget{{{BG_STYLE}}}")

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(14)

        # Left — current layout / workspace
        self._layout_label = QLabel("—")
        self._layout_label.setFont(FONT)
        self._layout_label.setStyleSheet(TEXT_STYLE)
        layout.addWidget(self._layout_label)

        layout.addStretch()

        # Center — live metrics
        for key, label in (
            ("camera_fps", "CAM"),
            ("hand_fps", "HAND"),
            ("memory_percent", "MEM"),
            ("cpu_percent", "CPU"),
        ):
            self._metric_labels[key] = label
            seg = QLabel(f"{label} 0")
            seg.setFont(FONT)
            seg.setStyleSheet(MUTED_STYLE)
            layout.addWidget(seg)
            self._metrics[key] = seg

        layout.addStretch()

        # Right — connection indicators (from snapshot readiness flags)
        for flag, caption in INDICATOR_LABELS:
            dot = QLabel("●")
            dot.setFont(FONT)
            dot.setStyleSheet(f"color: {INDICATOR_COLORS['inactive']};")
            caption_label = QLabel(caption)
            caption_label.setFont(FONT_MUTED)
            caption_label.setStyleSheet(MUTED_STYLE)

            group = QVBoxLayout()
            group.setSpacing(0)
            group.setContentsMargins(0, 0, 0, 0)
            dot.setAlignment(Qt.AlignHCenter)
            caption_label.setAlignment(Qt.AlignHCenter)
            group.addWidget(dot)
            group.addWidget(caption_label)

            container = QWidget()
            container.setLayout(group)
            layout.addWidget(container)
            self._indicators[flag] = dot

        # Hint
        hint = QLabel("Ctrl+Space")
        hint.setFont(FONT_MUTED)
        hint.setStyleSheet(MUTED_STYLE)
        layout.addWidget(hint)

    # ── Service wiring ─────────────────────────────────────────────

    def wire_services(self, command_bus: Any, event_bus: Any) -> None:
        """Backward-compatible alias for bind_context()."""
        self.bind_context(UIContext(command_bus=command_bus, event_bus=event_bus))

    def bind_context(self, context: UIContext) -> None:
        """Subscribe to SYSTEM_METRICS (and layout events). Pure view."""
        self._command_bus = context.command_bus
        self._event_bus = context.event_bus
        if context.event_bus is None:
            return
        try:
            context.event_bus.subscribe(EventType.SYSTEM_METRICS, self._on_metrics)
            context.event_bus.subscribe(EventType.WORKSPACE_LOADED, self._on_layout_event)
            context.event_bus.subscribe(EventType.LAYOUT_LOADED, self._on_layout_event)
        except Exception:
            pass

    def unwire(self) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.unsubscribe(EventType.SYSTEM_METRICS, self._on_metrics)
            self._event_bus.unsubscribe(EventType.WORKSPACE_LOADED, self._on_layout_event)
            self._event_bus.unsubscribe(EventType.LAYOUT_LOADED, self._on_layout_event)
        except Exception:
            pass
        self._event_bus = None

    # ── Events ─────────────────────────────────────────────────────

    def _on_metrics(self, event) -> None:
        snapshot = event.payload
        if isinstance(snapshot, PerformanceSnapshot):
            self.set_data(snapshot)

    def _on_layout_event(self, event) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        name = payload.get("name") or payload.get("layout") or ""
        if name:
            self._layout_label.setText(f"Layout: {name}")

    # ── Rendering ──────────────────────────────────────────────────

    def set_data(self, snapshot: PerformanceSnapshot) -> None:
        """Render a snapshot. Pure view — no service access."""
        for key, label in self._metrics.items():
            value = getattr(snapshot, key, None)
            if value is None:
                continue
            display = self._metric_labels.get(key, key.upper())
            if isinstance(value, float):
                label.setText(f"{display} {value:.0f}")
            else:
                label.setText(f"{display} {value}")

        for flag, dot in self._indicators.items():
            ready = bool(getattr(snapshot, flag, False))
            color = INDICATOR_COLORS["ready"] if ready else INDICATOR_COLORS["inactive"]
            dot.setStyleSheet(f"color: {color};")
