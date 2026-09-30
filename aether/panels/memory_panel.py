"""MemoryPanel — view-only panel for searching and viewing memory records.

View-only pattern:
    - Dispatches commands through CommandBus (memory.search, memory.recall)
    - Subscribes to events through EventBus (memory.query.completed)
    - Never accesses MemoryManager or repositories directly
    - Never mutates application state
    - Pure renderer: receives data, displays it

Sprint 1 (A-Lite):
    - Search bar → dispatches memory.search
    - Results list → shows matching records
    - Detail pane → shows selected record details

Future sprints:
    - Filter, Pin, Tag, Timeline, Graph, Preview
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from aether.ui.panel.abstract_panel import AbstractPanel
from aether.ui.panel.panel_info import PanelCapability


@dataclass
class MemoryPanelItem:
    """A single result item displayed in the panel."""

    key: str
    value: str
    memory_type: str = "semantic"
    confidence: float = 0.0
    position: Optional[Dict[str, float]] = None
    label: str = ""
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "type": self.memory_type,
            "confidence": self.confidence,
            "position": self.position,
            "label": self.label,
            "last_seen": self.last_seen,
        }


class MemoryPanel(AbstractPanel):
    """View-only memory panel.

    Dispatches commands for all user actions.
    Subscribes to memory events to refresh results.
    """

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 400,
        height: int = 300,
    ) -> None:
        super().__init__(
            panel_id="memory",
            x=x,
            y=y,
            width=width,
            height=height,
            z_index=20,
        )
        self._items: List[MemoryPanelItem] = []
        self._search_query: str = ""
        self._selected_key: Optional[str] = None
        self._selected_detail: Optional[Dict[str, Any]] = None
        self._command_bus = None
        self._event_bus = None

    # ── View-only public API ───────────────────────────────────────

    def wire_services(self, command_bus: Any, event_bus: Any) -> None:
        """Wire up command and event buses.

        Called by GUIPlugin during panel registration.
        This is the ONLY method that touches services.
        """
        self._command_bus = command_bus
        self._event_bus = event_bus
        self._subscribe()

    def set_search_query(self, query: str) -> None:
        """User typed in search bar — dispatch command."""
        self._search_query = query
        if self._command_bus:
            from aether.core.command import Command
            self._command_bus.dispatch(Command(
                name="memory.search",
                source="memory_panel",
                params={"query": query},
            ))

    def _subscribe(self) -> None:
        """Subscribe to memory query results."""
        if not self._event_bus:
            return
        try:
            self._event_bus.subscribe("memory.query.completed", self._on_query_completed)
            self._event_bus.subscribe("memory.semantic.created", self._on_memory_stored)
            self._event_bus.subscribe("memory.deleted", self._on_memory_deleted)
        except Exception:
            pass

    def _on_query_completed(self, event: Any) -> None:
        """Handle memory.search results."""
        payload = event.payload if hasattr(event, "payload") else {}
        records = payload.get("records", []) if isinstance(payload, dict) else []
        self._items = []
        for r in records:
            raw_value = r.get("value", "")
            if isinstance(raw_value, (dict, list)):
                value_str = json.dumps(raw_value, ensure_ascii=False)
            else:
                value_str = str(raw_value)
            pos = None
            if "x" in r and "y" in r:
                pos = {"x": r.get("x", 0.0), "y": r.get("y", 0.0), "z": r.get("z", 0.0)}
            self._items.append(MemoryPanelItem(
                key=r.get("key", ""),
                value=value_str,
                memory_type=r.get("memory_type", "semantic"),
                confidence=r.get("confidence", 0.0),
                position=pos,
                label=r.get("label", ""),
            ))

    def _on_memory_stored(self, event: Any) -> None:
        """Refresh search when new memory is stored."""
        if self._search_query:
            self.set_search_query(self._search_query)

    def _on_memory_deleted(self, event: Any) -> None:
        """Refresh search when memory is deleted."""
        if self._search_query:
            self.set_search_query(self._search_query)

    # ── Data access (for rendering) ─────────────────────────────────

    def get_items(self) -> List[MemoryPanelItem]:
        """Get all current search results."""
        return list(self._items)

    def select_item(self, key: str) -> None:
        """User clicked a result — dispatch recall command."""
        self._selected_key = key
        if self._command_bus:
            from aether.core.command import Command
            self._command_bus.dispatch(Command(
                name="memory.recall",
                source="memory_panel",
                params={"key": key},
            ))
            self._selected_detail = {"key": key, "status": "loading..."}

    def set_detail(self, detail: Optional[Dict[str, Any]]) -> None:
        """Set the detail view data (called from event handler)."""
        self._selected_detail = detail

    def get_selected_key(self) -> Optional[str]:
        return self._selected_key

    def get_detail(self) -> Optional[Dict[str, Any]]:
        return self._selected_detail

    def item_count(self) -> int:
        return len(self._items)

    # ── IPanel interface ───────────────────────────────────────────

    def update(self) -> None:
        pass

    def paint(self) -> None:
        pass
