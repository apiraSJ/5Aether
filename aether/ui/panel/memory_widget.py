"""MemoryPanelWidget — real Qt widget for the Memory panel.

Layout:
    ┌──────────────────────────────────────────────────────┐
    │ [Search...]                     [Recent][Pinned]    │
    │ Suggestions:  gesture  camera  workspace  memory   │
    ├────────────────────────────┬─────────────────────────┤
    │ ⭐ AI roadmap             │ Title                   │
    │ ⭐ Workspace design        │ Summary, tags, source   │
    │ Sprint 1.5 complete       │ Content...               │
    │ Camera calibration        │              [Pin][Del] │
    └────────────────────────────┴─────────────────────────┘

Architecture:
    MemoryPanelWidget → MemoryController → MemoryService → MemoryManager

The widget is a thin view. All data comes from the controller; it never
touches services or the event bus directly.
"""

from __future__ import annotations

import html as html_lib
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLineEdit, QListWidget, QListWidgetItem, QTextBrowser, QLabel,
    QPushButton, QButtonGroup,
)

from aether.memory.seed_data import SUGGESTIONS
from aether.ui.panel.panel_widget import PanelWidget
from aether.ui.ui_context import UIContext

FONT_SEARCH = QFont("Segoe UI Variable", 9)
FONT_LIST = QFont("Segoe UI Variable", 9)
FONT_DETAIL = QFont("Segoe UI Variable", 9)

SEARCH_DEBOUNCE_MS = 250

# Source → icon (flat design glyphs)
_SOURCE_ICONS = {
    "workspace": "\U0001F5A5",   # 🖥
    "vision": "\U0001F441",      # 👁
    "interaction": "\U0001F932", # 🤲
    "gesture": "\U0001F932",     # 🤲
    "system": "\u2699",          # ⚙
    "camera": "\U0001F4F7",      # 📷
}


def _source_icon(source: str) -> str:
    return _SOURCE_ICONS.get(str(source).lower(), "\U0001F4A1")  # 💡


class MemoryPanelWidget(PanelWidget):
    """Memory panel with search, suggestions, recent/pinned views, and detail."""

    def __init__(self, panel_id: str, panel_type: str, label: str, parent=None) -> None:
        self._controller = None
        self._items: List[Dict[str, Any]] = []
        self._selected_id: Optional[str] = None
        super().__init__(panel_id, panel_type, label, parent)

    def _build_content(self) -> None:
        layout = self._content_layout

        # Search bar + view switch
        top = QHBoxLayout()
        top.setSpacing(4)

        self._search = QLineEdit()
        self._search.setPlaceholderText("\U0001F50D  Search memories...")
        self._search.setStyleSheet(self._search_style())
        top.addWidget(self._search, 1)

        self._view_recent = QPushButton("Recent")
        self._view_pinned = QPushButton("Pinned")
        for btn in (self._view_recent, self._view_pinned):
            btn.setCheckable(True)
            btn.setStyleSheet(self._chip_style())
        self._view_recent.setChecked(True)
        self._view_group = QButtonGroup(self)
        self._view_group.addButton(self._view_recent)
        self._view_group.addButton(self._view_pinned)
        self._view_group.buttonClicked.connect(self._on_view_changed)
        top.addWidget(self._view_recent)
        top.addWidget(self._view_pinned)
        layout.addLayout(top)

        # Suggestion chips
        self._suggestion_row = QHBoxLayout()
        self._suggestion_row.setSpacing(4)
        hint = QLabel("Suggestions:")
        hint.setStyleSheet("color: rgba(140, 150, 180, 200); font-size: 8px;")
        self._suggestion_row.addWidget(hint)
        self._suggestion_buttons: List[QPushButton] = []
        for s in SUGGESTIONS:
            btn = QPushButton(s)
            btn.setStyleSheet(self._chip_style())
            btn.clicked.connect(lambda _=False, t=s: self._apply_suggestion(t))
            self._suggestion_row.addWidget(btn)
            self._suggestion_buttons.append(btn)
        self._suggestion_row.addStretch()
        layout.addLayout(self._suggestion_row)

        # Splitter: results list | detail
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._list = QListWidget()
        self._list.setStyleSheet(self._list_style())
        self._list.currentItemChanged.connect(self._on_select)
        splitter.addWidget(self._list)

        # Detail pane
        detail_box = QWidget()
        detail_box.setStyleSheet("background: transparent;")
        detail_layout = QVBoxLayout(detail_box)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(4)

        self._detail = QTextBrowser()
        self._detail.setStyleSheet(self._detail_style())
        detail_layout.addWidget(self._detail, 1)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        self._pin_btn = QPushButton("\u2B50 Pin")
        self._delete_btn = QPushButton("\u2715 Delete")
        self._pin_btn.setStyleSheet(self._action_style())
        self._delete_btn.setStyleSheet(self._action_style())
        self._pin_btn.clicked.connect(self._on_pin_toggle)
        self._delete_btn.clicked.connect(self._on_delete)
        actions.addWidget(self._pin_btn)
        actions.addStretch()
        actions.addWidget(self._delete_btn)
        detail_layout.addLayout(actions)

        splitter.addWidget(detail_box)
        splitter.setSizes([190, 250])

        layout.addWidget(splitter, 1)

        # Debounced search
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._run_search)
        self._search.textChanged.connect(self._on_search_text)

    def _on_mount(self) -> None:
        if self._controller is not None:
            self._refresh()

    def wire_services(self, command_bus=None, event_bus=None) -> None:
        """Backward-compatible alias for bind_context()."""
        self.bind_context(UIContext(command_bus=command_bus, event_bus=event_bus))

    def bind_context(self, context: UIContext) -> None:
        self._command_bus = context.command_bus
        self._event_bus = context.event_bus

    def wire_controller(self, controller) -> None:
        """Attach the MemoryController (functional service facade)."""
        self._controller = controller
        self._refresh()

    def update_content(self) -> None:
        """Refresh the panel from the controller."""
        self._refresh()

    # ── Data loading ──────────────────────────────────────────────

    def _refresh(self) -> None:
        if self._controller is None:
            return
        query = self._search.text().strip()
        if query:
            items = self._controller.search(query)
        elif self._view_pinned.isChecked():
            items = self._controller.pinned()
        else:
            items = self._controller.recent()
        self._items = items
        self._refresh_list()
        if not self._selected_id and items:
            self._list.setCurrentRow(0)
        elif self._selected_id:
            for i, item in enumerate(items):
                if item.get("id") == self._selected_id:
                    self._list.setCurrentRow(i)
                    break

    def _refresh_list(self) -> None:
        self._list.clear()
        if not self._items:
            if self._search.text().strip():
                placeholder = QListWidgetItem(f"No memories found for '{self._search.text().strip()}'")
            elif self._view_pinned.isChecked():
                placeholder = QListWidgetItem("No pinned memories yet")
            else:
                placeholder = QListWidgetItem("No memories yet")
            placeholder.setFlags(Qt.NoItemFlags)
            placeholder.setForeground(Qt.gray)
            self._list.addItem(placeholder)
            self._render_empty_detail()
            return

        for item in self._items:
            pinned = bool(item.get("pinned"))
            source = str(item.get("source") or "unknown")
            title = str(item.get("title") or item.get("key") or "Untitled")
            display = f"{'\u2B50 ' if pinned else ''}{_source_icon(source)} {title}"
            li = QListWidgetItem(display)
            li.setData(Qt.UserRole, item)
            li.setToolTip(str(item.get("summary") or ""))
            self._list.addItem(li)

    # ── Detail rendering ──────────────────────────────────────────

    def _render_detail(self, item: Dict[str, Any]) -> None:
        self._selected_id = item.get("id")
        title = html_lib.escape(str(item.get("title") or item.get("key") or "Untitled"))
        summary = html_lib.escape(str(item.get("summary") or ""))
        content = html_lib.escape(str(item.get("content") or ""))
        tags = item.get("tags") or []
        source = html_lib.escape(str(item.get("source") or "unknown"))
        pinned = bool(item.get("pinned"))
        importance = int(item.get("importance", 0))
        updated = self._format_time(item.get("updated_at"))

        tag_html = " ".join(
            f'<span style="background:rgba(96,165,250,40);color:#7ab7ff;'
            f'border-radius:3px;padding:1px 6px;font-size:8px;">{html_lib.escape(t)}</span>'
            for t in tags
        )

        html_text = (
            f"<div style='font-size:12px;font-weight:600;color:#e8ecf5;'>{_source_icon(source)} {title}</div>"
            f"{'<div style=\'color:#ffb347;font-size:9px;\'>&#9733; Pinned</div>' if pinned else ''}"
            f"<div style='color:#aab4cf;font-size:9px;margin-top:2px;'>{summary}</div>"
            f"<div style='color:#6f7c9c;font-size:8px;margin-top:4px;'>"
            f"{source} &middot; importance {importance} &middot; updated {updated}"
            f"</div>"
            f"{'<div style=\'margin-top:4px;\'>' + tag_html + '</div>' if tag_html else ''}"
            f"<hr style='color:#3a4260;'>"
            f"<div style='color:#c6cedf;font-size:9px;'>{content}</div>"
        )
        self._detail.setHtml(html_text)
        self._pin_btn.setText("\u2B50 Unpin" if pinned else "\u2B50 Pin")

    def _render_empty_detail(self) -> None:
        query = self._search.text().strip()
        if query:
            message = f"No memories found for &quot;{html_lib.escape(query)}&quot;"
        elif self._view_pinned.isChecked():
            message = "No pinned memories yet"
        else:
            message = "No memories yet"
        html_text = (
            f"<div style='text-align:center;color:#6f7c9c;font-size:10px;"
            f"padding-top:48px;'>&#128640;<br><br>{message}</div>"
        )
        self._detail.setHtml(html_text)
        self._selected_id = None
        self._pin_btn.setText("\u2B50 Pin")

    @staticmethod
    def _format_time(timestamp) -> str:
        try:
            import datetime
            return datetime.datetime.fromtimestamp(float(timestamp)).strftime("%b %d, %H:%M")
        except (TypeError, ValueError, OSError):
            return "—"

    # ── Events ────────────────────────────────────────────────────

    def _on_search_text(self, _text: str) -> None:
        # Loading flash: accent border while debounce timer is pending
        self._search.setStyleSheet(self._search_style(loading=True))
        self._search_timer.start()

    def _run_search(self) -> None:
        self._search.setStyleSheet(self._search_style(loading=False))
        self._refresh()

    def _apply_suggestion(self, suggestion: str) -> None:
        self._search.setText(suggestion)
        self._run_search()

    def _on_view_changed(self, _button) -> None:
        self._refresh()

    def _on_select(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if current is None:
            return
        item = current.data(Qt.UserRole)
        if item:
            self._render_detail(item)

    def _on_pin_toggle(self) -> None:
        if not self._selected_id or self._controller is None:
            return
        self._controller.toggle_pin(self._selected_id)
        self._refresh()
        self._flash_pin()

    def _flash_pin(self) -> None:
        """Gold flash on the pinned/unpinned row (flat design — no scale)."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            data = item.data(Qt.UserRole)
            if data and data.get("id") == self._selected_id:
                item.setBackground(QColor(255, 165, 0, 70))
                QTimer.singleShot(150, lambda it=item: it.setBackground(QColor(0, 0, 0, 0)))
                break

    def _on_delete(self) -> None:
        if not self._selected_id or self._controller is None:
            return
        self._controller.delete(self._selected_id)
        self._selected_id = None
        self._refresh()

    # ── Styles ────────────────────────────────────────────────────

    @staticmethod
    def _search_style(loading: bool = False) -> str:
        border = "rgba(96,165,250,220)" if loading else "rgba(60,65,85,160)"
        return (
            "QLineEdit{background:rgba(20,22,35,200);border:1px solid "
            f"{border};"
            "border-radius:4px;padding:4px 8px;color:rgba(200,210,230,220);"
            "font-size:9px;}"
        )

    @staticmethod
    def _chip_style() -> str:
        return (
            "QPushButton{background:rgba(40,45,65,160);border:1px solid rgba(60,65,85,140);"
            "border-radius:4px;padding:2px 8px;color:rgba(180,195,220,200);font-size:8px;}"
            "QPushButton:hover{background:rgba(96,165,250,50);}"
            "QPushButton:checked{background:rgba(96,165,250,90);border-color:rgba(96,165,250,180);}"
        )

    @staticmethod
    def _action_style() -> str:
        return (
            "QPushButton{background:rgba(40,45,65,160);border:1px solid rgba(60,65,85,140);"
            "border-radius:4px;padding:2px 8px;color:rgba(180,195,220,200);font-size:8px;}"
            "QPushButton:hover{background:rgba(96,165,250,50);}"
        )

    @staticmethod
    def _list_style() -> str:
        return (
            "QListWidget{background:transparent;border:1px solid rgba(60,65,85,100);"
            "border-radius:4px;color:rgba(200,210,230,200);font-size:9px;}"
            "QListWidget::item{padding:4px 6px;}"
            "QListWidget::item:selected{background:rgba(96,165,250,100);}"
            "QListWidget::item:hover{background:rgba(96,165,250,40);}"
        )

    @staticmethod
    def _detail_style() -> str:
        return (
            "QTextBrowser{background:transparent;border:1px solid rgba(60,65,85,100);"
            "border-radius:4px;color:rgba(200,210,230,200);font-size:9px;padding:4px;}"
        )
