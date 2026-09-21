"""TasksPanelWidget — real Qt widget for the Tasks panel.

Layout:
    ┌─────────────────────────────────────────────────┐
    │ ☑ Interaction layer done                        │
    │ ☐ AI Chat integration                           │
    │ ─────────────────────────────────────────────── │
    │ [ New task…                    ] [+]            │
    └─────────────────────────────────────────────────┘

Backend: task list persists via PanelSession (session.state["tasks"]),
         survives widget destroy/recreate and app restart.
"""

from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QWidget,
)

from aether.ui.panel.panel_widget import PanelWidget
from aether.ui.ui_context import UIContext


class TasksPanelWidget(PanelWidget):
    """Tasks panel with a checkable todo list + new-task input."""

    def __init__(self, panel_id: str, panel_type: str, label: str, parent=None) -> None:
        self._command_bus = None
        self._event_bus = None
        self._session = None
        super().__init__(panel_id, panel_type, label, parent)

    def _build_content(self) -> None:
        layout = self._content_layout

        self._list = QListWidget()
        self._list.setStyleSheet(self._list_style())
        self._list.itemChanged.connect(self._on_toggle)
        layout.addWidget(self._list, 1)

        # Input row
        row = QHBoxLayout()
        row.setSpacing(4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("New task…")
        self._input.setStyleSheet(self._input_style())
        self._input.returnPressed.connect(self._on_add_task)
        row.addWidget(self._input, 1)

        self._add_btn = QPushButton("\uFF0B")  # ＋
        self._add_btn.setFixedSize(26, 26)
        self._add_btn.setStyleSheet(self._button_style())
        self._add_btn.setToolTip("Add task")
        self._add_btn.clicked.connect(self._on_add_task)
        row.addWidget(self._add_btn)

        layout.addLayout(row)

    # ── PanelSession binding ──────────────────────────────────────

    def bind_session(self, session) -> None:
        """Attach the persistent session and restore tasks from it."""
        self._session = session
        saved = session.load_state("tasks") if session else None
        if saved:
            self._restore_tasks(saved)
        else:
            self._populate_defaults()

    def _restore_tasks(self, tasks) -> None:
        self._list.clear()
        for task in tasks:
            if not isinstance(task, dict):
                continue
            self._add_item(task.get("label", ""), bool(task.get("done", False)))

    def _populate_defaults(self) -> None:
        items = [
            ("Interaction layer done",         True),
            ("Workspace renderer done",        True),
            ("Memory panel content",           False),
            ("AI Chat integration",            False),
            ("Voice commands",                 False),
            ("Performance tuning",             False),
        ]
        for label, done in items:
            self._add_item(label, done)

    # ── Task operations ───────────────────────────────────────────

    def _add_item(self, label: str, done: bool) -> None:
        item = QListWidgetItem()
        item.setText(label)
        item.setCheckState(Qt.Checked if done else Qt.Unchecked)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        self._list.addItem(item)

    def _on_add_task(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._add_item(text, False)
        self._input.clear()
        self._save_state()

    def _on_toggle(self, item: QListWidgetItem) -> None:
        done = item.checkState() == Qt.Checked
        color = QColor(96, 165, 250, 200) if done else QColor(100, 110, 140, 180)
        item.setForeground(color)
        self._save_state()

    def _current_tasks(self) -> list[dict]:
        tasks = []
        for i in range(self._list.count()):
            item = self._list.item(i)
            tasks.append({
                "label": item.text(),
                "done": item.checkState() == Qt.Checked,
            })
        return tasks

    def _save_state(self) -> None:
        if self._session:
            self._session.save_state("tasks", self._current_tasks())

    # ── Services ──────────────────────────────────────────────────

    def wire_services(self, command_bus: Any, event_bus: Any) -> None:
        """Backward-compatible alias for bind_context()."""
        self.bind_context(UIContext(command_bus=command_bus, event_bus=event_bus))

    def bind_context(self, context: UIContext) -> None:
        self._command_bus = context.command_bus
        self._event_bus = context.event_bus

    # ── Styles ────────────────────────────────────────────────────

    @staticmethod
    def _list_style() -> str:
        return (
            "QListWidget{background:transparent;border:1px solid rgba(60,65,85,100);"
            "border-radius:4px;color:rgba(200,210,230,200);font-size:9px;}"
            "QListWidget::item{padding:6px 8px;}"
            "QListWidget::item:selected{background:rgba(96,165,250,100);}"
            "QListWidget::item:hover{background:rgba(96,165,250,40);}"
        )

    @staticmethod
    def _input_style() -> str:
        return (
            "QLineEdit{background:rgba(20,22,35,200);border:1px solid rgba(60,65,85,120);"
            "border-radius:4px;padding:4px 8px;color:rgba(200,210,230,200);font-size:9px;}"
            "QLineEdit:focus{border:1px solid rgba(96,165,250,180);}"
        )

    @staticmethod
    def _button_style() -> str:
        return (
            "QPushButton{background:rgba(96,165,250,60);border:1px solid rgba(96,165,250,120);"
            "border-radius:4px;color:rgba(200,210,230,220);font-size:14px;}"
            "QPushButton:hover{background:rgba(96,165,250,110);}"
        )