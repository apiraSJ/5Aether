"""CommandPaletteWidget — Ctrl+Space / Ctrl+K command palette for Aether.

Sections:
    Commands  — registered commands (CommandRegistry)
    Panels    — registered workspace panels (PanelRegistry)
    Layouts   — saved layout names (WorkspaceManager)
    Memory    — quick memory search suggestions
    Recent    — recently executed palette commands

Architecture:
    CommandPaletteWidget is a thin view. Selecting an entry dispatches a
    Command on the CommandBus (source="palette"). Natural-language input
    that matches no entry is routed via CLI_INPUT_RECEIVED so it flows
    through IntentResolver → CommandBus (same pipeline as CLI/Voice/AI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from aether.memory.seed_data import SUGGESTIONS
from aether.ui.ui_context import UIContext

PALETTE_WIDTH = 620
PALETTE_HEIGHT = 420
MAX_ENTRIES = 200


@dataclass
class PaletteEntry:
    """A single selectable palette item."""

    section: str
    title: str
    subtitle: str = ""
    command: str = ""  # command name to dispatch
    params: dict[str, Any] = field(default_factory=dict)

    def match_text(self) -> str:
        return f"{self.section} {self.title} {self.subtitle} {self.command}".lower()


class CommandPaletteWidget(QWidget):
    """Floating command palette: search box + result list."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._command_bus = None
        self._command_registry = None
        self._panel_registry = None
        self._workspace_manager = None
        self._memory_service = None
        self._entries: list[PaletteEntry] = []
        self._recent: list[str] = []
        self._visible = False

        self.setWindowFlags(Qt.SubWindow | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFixedSize(PALETTE_WIDTH, PALETTE_HEIGHT)
        self.setStyleSheet(self._palette_style())
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("\u2318  Type a command, panel, layout, or memory query…")
        self._search.setStyleSheet(self._search_style())
        self._search.textChanged.connect(self._on_filter)
        layout.addWidget(self._search)

        self._results = QListWidget()
        self._results.setStyleSheet(self._list_style())
        self._results.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._results, 1)

        self._hint = self._hint_label()
        layout.addWidget(self._hint)

    # ── Public API ─────────────────────────────────────────────────

    def wire_services(
        self,
        command_bus: Any = None,
        event_bus: Any = None,
        command_registry: Any = None,
        panel_registry: Any = None,
        workspace_manager: Any = None,
        memory_service: Any = None,
    ) -> None:
        """Backward-compatible alias for bind_context()."""
        self.bind_context(UIContext(
            command_bus=command_bus,
            event_bus=event_bus,
            command_registry=command_registry,
            panel_registry=panel_registry,
            workspace_manager=workspace_manager,
            memory_service=memory_service,
        ))

    def bind_context(self, context: UIContext) -> None:
        self._command_bus = context.command_bus
        self._event_bus = context.event_bus
        self._command_registry = context.command_registry
        self._panel_registry = context.panel_registry
        self._workspace_manager = context.workspace_manager
        self._memory_service = context.memory_service

    def refresh(self) -> None:
        """Rebuild the entry list from current registries."""
        self._entries = self._collect_entries()
        self._apply_filter("")

    def open_palette(self) -> None:
        self.refresh()
        self.show()
        self.raise_()
        self._search.clear()
        self._search.setFocus()
        self._visible = True

    def close_palette(self) -> None:
        self.hide()
        self._visible = False

    def toggle(self) -> None:
        if self._visible and self.isVisible():
            self.close_palette()
        else:
            self.open_palette()

    @property
    def is_open(self) -> bool:
        return self._visible and self.isVisible()

    @property
    def entries(self) -> list[PaletteEntry]:
        return list(self._entries)

    # ── Entry collection ───────────────────────────────────────────

    def _collect_entries(self) -> list[PaletteEntry]:
        entries: list[PaletteEntry] = []

        # Commands
        if self._command_registry is not None:
            try:
                for category in self._command_registry.get_categories():
                    for name in self._command_registry.get_commands_in_category(category):
                        info = self._command_registry.resolve(name)
                        entries.append(PaletteEntry(
                            section="Commands",
                            title=name,
                            subtitle=(info.description if info else ""),
                            command=name,
                        ))
            except Exception:
                pass

        # Recent commands (most recent first, dedup)
        for name in self._recent:
            entries.append(PaletteEntry(
                section="Recent",
                title=name,
                subtitle="Re-run from palette",
                command=name,
            ))

        # Panels
        if self._panel_registry is not None:
            try:
                for info in self._panel_registry.list_all():
                    if info.id == "camera_panel":
                        continue  # camera is a background layer, not a panel
                    entries.append(PaletteEntry(
                        section="Panels",
                        title=info.id,
                        subtitle=f"{info.type} · {'visible' if info.visible else 'hidden'}",
                        command="ui.panel.focus",
                        params={"panel_id": info.id},
                    ))
            except Exception:
                pass

        # Layouts
        if self._workspace_manager is not None:
            try:
                for name in self._workspace_manager.list_layouts():
                    current = " · active" if name == self._workspace_manager.current_layout() else ""
                    entries.append(PaletteEntry(
                        section="Layouts",
                        title=name,
                        subtitle=f"Restore layout{current}",
                        command="ui.layout.load",
                        params={"name": name},
                    ))
            except Exception:
                pass

        # Memory suggestions
        for s in SUGGESTIONS:
            entries.append(PaletteEntry(
                section="Memory",
                title=s,
                subtitle="Search memory",
                command="memory.search",
                params={"query": s},
            ))

        return entries

    # ── Filtering ──────────────────────────────────────────────────

    def _on_filter(self, text: str) -> None:
        self._apply_filter(text)

    def _apply_filter(self, query: str) -> None:
        self._results.clear()
        q = query.strip().lower()
        shown = 0
        for entry in self._entries:
            if q and q not in entry.match_text():
                continue
            if shown >= MAX_ENTRIES:
                break
            item = QListWidgetItem(self._format_entry(entry))
            item.setData(Qt.UserRole, entry)
            item.setToolTip(entry.subtitle)
            self._results.addItem(item)
            shown += 1

    @staticmethod
    def _format_entry(entry: PaletteEntry) -> str:
        subtitle = f" — {entry.subtitle}" if entry.subtitle else ""
        return f"[{entry.section}]  {entry.title}{subtitle}"

    # ── Selection ──────────────────────────────────────────────────

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.UserRole)
        if entry:
            self._execute(entry)

    def _execute(self, entry: PaletteEntry) -> None:
        if entry.section == "Recent" or (entry.section == "Commands" and entry.command):
            self._push_recent(entry.command)
        if entry.command and self._command_bus is not None:
            from aether.core.command import Command
            self._command_bus.dispatch(Command(
                name=entry.command,
                source="palette",
                params=dict(entry.params),
            ))
        self.close_palette()

    def _push_recent(self, command_name: str) -> None:
        if command_name in self._recent:
            self._recent.remove(command_name)
        self._recent.insert(0, command_name)
        self._recent = self._recent[:10]

    def run_natural_input(self, text: str) -> None:
        """Route free-form input through the intent pipeline."""
        if not text.strip():
            return
        if self._event_bus:
            from aether.core.event_bus_v2 import Event
            from aether.core.event_type import EventType
            self._event_bus.publish(Event(
                type=EventType.CLI_INPUT_RECEIVED,
                payload={"text": text, "context": "palette"},
                source="command_palette",
            ))

    # ── Keyboard ───────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.close_palette()
            event.accept()
            return
        if event.key() == Qt.Key_Down:
            self._move_selection(1)
            event.accept()
            return
        if event.key() == Qt.Key_Up:
            self._move_selection(-1)
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            item = self._results.currentItem()
            if item is not None:
                entry = item.data(Qt.UserRole)
                if entry:
                    self._execute(entry)
            else:
                self.run_natural_input(self._search.text())
            event.accept()
            return
        super().keyPressEvent(event)

    def _move_selection(self, delta: int) -> None:
        row = self._results.currentRow()
        count = self._results.count()
        if count == 0:
            return
        new_row = max(0, min(count - 1, row + delta))
        self._results.setCurrentRow(new_row)
        self._results.scrollToItem(self._results.currentItem())

    # ── Styles ─────────────────────────────────────────────────────

    @staticmethod
    def _palette_style() -> str:
        return "QWidget{background:rgba(18,20,32,245);border:1px solid rgba(96,165,250,120);border-radius:8px;}"

    @staticmethod
    def _search_style() -> str:
        return (
            "QLineEdit{background:rgba(28,32,48,220);border:1px solid rgba(96,165,250,160);"
            "border-radius:5px;padding:8px 10px;color:rgba(220,228,245,230);font-size:13px;}"
        )

    @staticmethod
    def _list_style() -> str:
        return (
            "QListWidget{background:transparent;border:none;color:rgba(200,210,230,220);"
            "font-size:11px;outline:none;}"
            "QListWidget::item{padding:5px 8px;border-radius:4px;}"
            "QListWidget::item:selected{background:rgba(96,165,250,100);color:#fff;}"
            "QListWidget::item:hover{background:rgba(96,165,250,40);}"
        )

    @staticmethod
    def _hint_label() -> Any:
        from PySide6.QtWidgets import QLabel
        hint = QLabel(
            "\u2191\u2193 navigate    \u21B5 execute    Esc close"
        )
        hint.setStyleSheet("color: rgba(140, 150, 180, 180); font-size: 9px;")
        hint.setAlignment(Qt.AlignCenter)
        return hint
