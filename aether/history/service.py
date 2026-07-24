"""HistoryService — records command lifecycle for UI, dashboard, and debugging."""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, List, Optional

from aether.core.service import IService

logger = logging.getLogger("Aether.HistoryService")


@dataclass(frozen=True)
class HistoryEntry:
    """Immutable record of a single command's lifecycle."""

    command: str
    command_id: str
    source: str
    status: str
    params: dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


class HistoryService(IService):
    """Stores command history entries. Subscribes to command.* events via EventBus."""

    def __init__(self, max_entries: int = 200) -> None:
        self._entries: Deque[HistoryEntry] = deque(maxlen=max_entries)
        self._started = False
        self._event_bus = None

    def start(self) -> None:
        if self._started:
            return
        logger.info("HistoryService started")

    def update(self, dt: float) -> None:
        pass

    def stop(self) -> None:
        if not self._started:
            return
        logger.info("HistoryService stopping (%d entries)", len(self._entries))
        self._started = False

    def set_event_bus(self, event_bus) -> None:
        """Subscribe to command lifecycle events."""
        self._event_bus = event_bus
        event_bus.subscribe("command.completed", self._on_command_completed)
        event_bus.subscribe("command.failed", self._on_command_failed)
        self._started = True

    def _on_command_completed(self, event) -> None:
        p = event.payload
        self._entries.append(HistoryEntry(
            command=p.get("command", "?"),
            command_id=p.get("command_id", ""),
            source=p.get("source", "?"),
            status="OK",
            params=p.get("params", {}),
            result=p.get("result"),
            duration_ms=p.get("duration_ms", 0),
        ))

    def _on_command_failed(self, event) -> None:
        p = event.payload
        self._entries.append(HistoryEntry(
            command=p.get("command", "?"),
            command_id=p.get("command_id", ""),
            source=p.get("source", "?"),
            status="FAIL",
            params=p.get("params", {}),
            error=p.get("error"),
            duration_ms=p.get("duration_ms", 0),
        ))

    # --- Query API ---

    def get_recent(self, limit: int = 50) -> List[HistoryEntry]:
        entries = list(self._entries)
        return entries[-limit:]

    def get_count(self) -> int:
        return len(self._entries)

    def get_ok_count(self) -> int:
        return sum(1 for e in self._entries if e.status == "OK")

    def get_fail_count(self) -> int:
        return sum(1 for e in self._entries if e.status == "FAIL")

    def get_last(self) -> Optional[HistoryEntry]:
        return self._entries[-1] if self._entries else None

    def clear(self) -> int:
        count = len(self._entries)
        self._entries.clear()
        return count