"""MemoryPanel — displays remembered objects and their spatial data.

Stateless renderer — reads from its data model (list of remembered items).
The model is updated by MemoryService via EventBus or direct injection.

Panel type: 'memory'
Z-index: 20
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from aether.ui.panel.abstract_panel import AbstractPanel
from aether.ui.panel.panel_info import PanelCapability


@dataclass
class MemoryItem:
    """A single remembered item displayed in the panel."""

    id: str
    name: str
    description: str = ""
    position: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.0
    last_seen: float = field(default_factory=time.time)
    source: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "position": self.position,
            "tags": self.tags,
            "confidence": self.confidence,
            "last_seen": self.last_seen,
            "source": self.source,
        }


class MemoryPanel(AbstractPanel):
    """Displays remembered objects in a list.

    Stateless renderer — reads from _items list.
    Updated by MemoryService events or direct injection.
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
        self._items: List[MemoryItem] = []
        self._filter: str = ""
        self._sort_by: str = "name"  # name, confidence, last_seen

    # ── Data model ─────────────────────────────────────────────────

    def set_items(self, items: List[MemoryItem]) -> None:
        """Replace all items (called by MemoryService)."""
        self._items = list(items)

    def add_item(self, item: MemoryItem) -> None:
        """Add or update an item."""
        for i, existing in enumerate(self._items):
            if existing.id == item.id:
                self._items[i] = item
                return
        self._items.append(item)

    def remove_item(self, item_id: str) -> bool:
        """Remove an item by id."""
        for i, item in enumerate(self._items):
            if item.id == item_id:
                self._items.pop(i)
                return True
        return False

    def get_items(self) -> List[MemoryItem]:
        """Get all items, optionally filtered."""
        items = self._items
        if self._filter:
            f = self._filter.lower()
            items = [i for i in items if f in i.name.lower() or f in i.description.lower()]
        if self._sort_by == "confidence":
            items = sorted(items, key=lambda i: i.confidence, reverse=True)
        elif self._sort_by == "last_seen":
            items = sorted(items, key=lambda i: i.last_seen, reverse=True)
        else:
            items = sorted(items, key=lambda i: i.name.lower())
        return items

    def set_filter(self, text: str) -> None:
        """Set a text filter for displayed items."""
        self._filter = text

    def set_sort(self, sort_by: str) -> None:
        """Set sort order: 'name', 'confidence', 'last_seen'."""
        self._sort_by = sort_by

    def item_count(self) -> int:
        return len(self._items)

    # ── IPanel interface ───────────────────────────────────────────

    def update(self) -> None:
        """Update panel state. No-op for now — data injected externally."""
        pass

    def paint(self) -> None:
        """Render the panel. No-op for now — Qt widget will handle rendering."""
        pass
