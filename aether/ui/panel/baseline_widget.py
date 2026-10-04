"""BaselinePanelWidget — real Qt widget for the M1 Determinnistic Baseline panel.

Layout:
    ┌────────────────────────────────────────────────┐
    │ Component slots:   [1][2][3][4][5]             │
    │                     (stylized buttons)         │
    │ [ Capture ]                                    │
    │ Status: Selected Circuit Breaker Panel (CB-100)│
    │ ┌────────────────────────────────────────────┐ │
    │ │ Baseline catalog (captured / pending)      │ │
    │ │  #1 Circuit Breaker Panel — captured       │ │
    │ │  #2 Backup Power Supply   — pending        │ │
    │ └────────────────────────────────────────────┘ │
    └────────────────────────────────────────────────┘

Backend: dispatches baseline.select / baseline.capture / baseline.list via
CommandBus (BaselinePlugin), receives baseline.selected / baseline.captured
via EventBus to refresh the list.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from aether.sandbox.catalog import COMPONENTS
from aether.ui.panel.panel_widget import PanelWidget
from aether.ui.ui_context import UIContext


class BaselinePanelWidget(PanelWidget):
    """Baseline panel: choose a component, capture a snapshot, list baselines."""

    def __init__(self, panel_id: str, panel_type: str, label: str, parent=None) -> None:
        self._command_bus = None
        self._event_bus = None
        self._selected_id: Optional[str] = None
        super().__init__(panel_id, panel_type, label, parent)

    # ── Content ──────────────────────────────────────────────────

    def _build_content(self) -> None:
        layout = self._content_layout

        slot_row = QGridLayout()
        slot_row.setSpacing(4)
        for col, comp in enumerate(COMPONENTS):
            btn = QPushButton(f"{comp['id']}")
            btn.setToolTip(comp["name"])
            btn.setFixedHeight(32)
            btn.setStyleSheet(self._slot_style())
            btn.clicked.connect(lambda checked=False, cid=comp["id"]: self._select(cid))
            setattr(self, f"_slot_{comp['id']}", btn)
            slot_row.addWidget(btn, 0, col)
        layout.addLayout(slot_row)

        self._capture_btn = QPushButton("Capture")
        self._capture_btn.setFixedHeight(28)
        self._capture_btn.setStyleSheet(self._capture_style())
        self._capture_btn.clicked.connect(self._capture)
        layout.addWidget(self._capture_btn)

        self._status = QLabel("No component selected")
        self._status.setStyleSheet("color: rgba(200, 210, 230, 200); font-size: 9px;")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._list = QTextBrowser()
        self._list.setStyleSheet(self._list_style())
        self._list.setOpenExternalLinks(False)
        layout.addWidget(self._list, 1)

    # ── Service binding ──────────────────────────────────────────

    def wire_services(self, command_bus: Any, event_bus: Any) -> None:
        """Backward-compatible alias for bind_context()."""
        self.bind_context(UIContext(command_bus=command_bus, event_bus=event_bus))

    def bind_context(self, context: UIContext) -> None:
        self._command_bus = context.command_bus
        self._event_bus = context.event_bus
        if self._event_bus is not None:
            # Subscribe once (idempotent) — refreshed on the main thread via
            # EventBus.flush() inside the tick.
            self._event_bus.subscribe("baseline.selected", self._on_selected)
            self._event_bus.subscribe("baseline.captured", self._on_captured)
        self.refresh()

    # ── Actions ──────────────────────────────────────────────────

    def _select(self, component_id: str) -> None:
        self._selected_id = component_id
        if self._command_bus is None:
            self._status.setText(f"Selected component {component_id} (command bus not bound)")
            return
        from aether.core.command import Command
        result = self._dispatch(Command(
            name="baseline.select", source="gui", params={"component_id": component_id},
        ))
        message = result.get("message", "") if isinstance(result, dict) else ""
        if message:
            self._status.setText(message)

    def _capture(self) -> None:
        if self._selected_id is None:
            self._status.setText("Select a component (1-5) before capturing.")
            return
        if self._command_bus is None:
            self._status.setText("[Capture] command bus not bound.")
            return
        from aether.core.command import Command
        result = self._dispatch(Command(
            name="baseline.capture", source="gui", params={"component_id": self._selected_id},
        ))
        message = result.get("message", "") if isinstance(result, dict) else ""
        if message:
            self._status.setText(f"● {message}")
        self.refresh()

    def refresh(self) -> None:
        """Pull the baseline catalog and render captured/pending state."""
        if self._command_bus is None:
            return
        from aether.core.command import Command
        result = self._dispatch(Command(name="baseline.list", source="gui", params={}))
        if not isinstance(result, dict):
            return
        entries = result.get("baselines")
        if isinstance(entries, list):
            self._render_entries(entries)
        elif result.get("message"):
            self._append(result.get("message"))

    def _on_selected(self, event) -> None:
        payload = event.payload if hasattr(event, "payload") else {}
        component_id = payload.get("component_id")
        if component_id:
            self._selected_id = str(component_id)
            self._status.setText(f"Selected component {component_id}: {payload.get('name', '')}")

    def _on_captured(self, event) -> None:
        self.refresh()

    # ── Rendering ────────────────────────────────────────────────

    def _render_entries(self, entries: list[dict]) -> None:
        self._list.clear()
        lines = ["Baseline catalog:"]
        for e in entries:
            state = "captured" if e.get("captured") else "pending"
            lines.append(f"  #{e['component_id']} {e['name']} — {state}")
        self._list.setPlainText("\n".join(lines))

    def _append(self, text: str) -> None:
        self._list.append(text)

    def _dispatch(self, command) -> dict:
        try:
            result = self._command_bus.dispatch_sync(command)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {"message": "[Baseline panel] not ready yet."}

    # ── Styles ───────────────────────────────────────────────────

    @staticmethod
    def _slot_style() -> str:
        return (
            "QPushButton{background:rgba(45,55,80,200);border:1px solid "
            "rgba(96,165,250,140);border-radius:4px;color:rgba(200,210,230,220);"
            "font-size:12px;font-weight:bold;}"
            "QPushButton:hover{background:rgba(60,75,110,220);}"
        )

    @staticmethod
    def _capture_style() -> str:
        return (
            "QPushButton{background:rgba(20,90,70,200);border:1px solid "
            "rgba(52,211,153,160);border-radius:4px;color:rgba(220,240,230,230);"
            "font-size:10px;}"
            "QPushButton:hover{background:rgba(28,120,95,220);}"
        )

    @staticmethod
    def _list_style() -> str:
        return (
            "QTextBrowser{background:transparent;border:1px solid rgba(60,65,85,100);"
            "border-radius:4px;color:rgba(200,210,230,200);font-size:9px;padding:6px;}"
        )