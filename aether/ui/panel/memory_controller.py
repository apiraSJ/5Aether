"""MemoryController — memory panel logic.

Architecture:
    MemoryWidget → MemoryController → MemoryService → MemoryManager

Handles user actions (search, recall, pin, delete) and state updates.
Pure Python — knows nothing about QWidget.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from aether.services.memory_service import MemoryService
from aether.ui.panel.panel_controller import PanelController

logger = logging.getLogger("Aether.MemoryController")


class MemoryController(PanelController):
    """Controller for the Memory panel."""

    def __init__(self, session, service: Optional[MemoryService] = None) -> None:
        super().__init__(session)
        self._service = service
        self._state = {}

    def wire_service(self, service: MemoryService) -> None:
        """Attach the functional memory service."""
        self._service = service

    @property
    def service(self) -> Optional[MemoryService]:
        return self._service

    # ── PanelController API ─────────────────────────────────────────

    def handle_action(self, action: str, **kwargs) -> Any:
        if action == "search":
            return self.search(kwargs.get("query", ""))
        if action == "recall":
            return self.recall(kwargs.get("id", ""))
        if action == "pin":
            return self.toggle_pin(kwargs.get("id", ""))
        if action == "delete":
            return self.delete(kwargs.get("id", ""))
        if action == "recent":
            return self.recent()
        if action == "pinned":
            return self.pinned()
        if action == "stats":
            return self.stats()
        if action == "focus":
            return None
        if action == "blur":
            return None
        logger.warning("MemoryController: unknown action %r", action)
        return None

    def get_state(self, key: str) -> Any:
        return self._state.get(key)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value

    # ── Domain actions ──────────────────────────────────────────────

    def search(self, query: str) -> List[Dict[str, Any]]:
        if not self._service:
            return []
        self.set_state("last_query", query)
        results = self._service.search(query)
        self.session.save_state("memory_query", query)
        return results

    def recall(self, record_id: str) -> Optional[Dict[str, Any]]:
        if not self._service:
            return None
        view = self._service.recall(record_id)
        if view:
            self.session.save_state("memory_recall_id", record_id)
        return view

    def recent(self) -> List[Dict[str, Any]]:
        if not self._service:
            return []
        return self._service.recent(limit=10)

    def pinned(self) -> List[Dict[str, Any]]:
        if not self._service:
            return []
        return self._service.pinned(limit=20)

    def toggle_pin(self, record_id: str) -> bool:
        if not self._service:
            return False
        existing = self._service.recall(record_id)
        if not existing:
            return False
        ok = self._service.set_pinned(record_id, not existing["pinned"])
        if ok:
            self.session.save_state("memory_pin_toggled", record_id)
        return ok

    def delete(self, record_id: str) -> bool:
        if not self._service:
            return False
        ok = self._service.delete(record_id)
        if ok:
            self.session.save_state("memory_deleted", record_id)
        return ok

    def stats(self) -> Dict[str, Any]:
        if not self._service:
            return {}
        return self._service.stats()
