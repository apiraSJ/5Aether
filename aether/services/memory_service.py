"""MemoryService — functional memory facade for the UI layer.

Architecture:
    MemoryWidget → MemoryController → MemoryService → MemoryManager → SQLite

Responsibilities:
    - Expose the locked UI API: search, recent, pinned, recall, add,
      update, delete, stats
    - Publish memory.* events on EventBus so AI/Voice/Gesture can
      subscribe later without touching this layer
    - Never expose SQLite or MemoryManager internals to widgets/controllers

This supersedes the Phase B in-memory demo in aether/memory/service.py
(which is unused). It returns plain dict views, not MemoryRecord objects,
so the UI never binds to storage internals.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from aether.core.event_bus_v2 import Event, EventBus
from aether.core.event_type import EventType
from aether.memory.memory_manager import MemoryManager
from aether.memory.models import MemoryRecord

logger = logging.getLogger("Aether.MemoryService")

EVENT_SOURCE = "memory.service"


def memory_record_to_view(record: MemoryRecord) -> Dict[str, Any]:
    """Convert a MemoryRecord into a plain UI-safe dict view.

    Metadata lives in record.context (title, summary, content, tags,
    importance, source, pinned). Falls back to record.key when metadata
    is missing so raw system records still render.
    """
    ctx = record.context or {}
    return {
        "id": record.id,
        "key": record.key,
        "title": ctx.get("title") or record.key,
        "summary": ctx.get("summary") or "",
        "content": ctx.get("content") or "",
        "tags": ctx.get("tags") or [],
        "importance": ctx.get("importance", 0),
        "source": ctx.get("source", ""),
        "pinned": bool(ctx.get("pinned", False)),
        "memory_type": record.memory_type,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


class MemoryService:
    """Functional memory facade for the UI layer."""

    def __init__(self, memory_manager: MemoryManager, event_bus: Optional[EventBus] = None) -> None:
        self._memory = memory_manager
        self._event_bus = event_bus

    # ── Event helpers ───────────────────────────────────────────────

    def _emit(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        if self._event_bus:
            try:
                self._event_bus.publish(Event(type=event_type, payload=payload, source=EVENT_SOURCE))
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Failed to publish %s: %s", event_type, e)

    # ── Locked UI API ───────────────────────────────────────────────

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Full-text search across semantic + episodic memory."""
        self._emit(EventType.MEMORY_SEARCH_REQUESTED, {"query": query})
        if not query or not query.strip():
            results = []
        else:
            result = self._memory.search(query.strip(), limit=20)
            results = [memory_record_to_view(r) for r in result.records]
        self._emit(EventType.MEMORY_SEARCH_COMPLETED, {
            "query": query,
            "count": len(results),
            "results": results,
        })
        return results

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Most recently updated records (semantic + episodic)."""
        result = self._memory.list_recent(limit=limit)
        return [memory_record_to_view(r) for r in result.records]

    def pinned(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Records flagged pinned."""
        result = self._memory.list_pinned(limit=limit)
        return [memory_record_to_view(r) for r in result.records]

    def recall(self, record_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single record by ID."""
        self._emit(EventType.MEMORY_RECALL_REQUESTED, {"id": record_id})
        record = self._memory.get(record_id)
        view = memory_record_to_view(record) if record else None
        self._emit(EventType.MEMORY_RECALL_COMPLETED, {
            "id": record_id,
            "found": view is not None,
            "record": view,
        })
        return view

    def add(self, memory: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Store a new semantic memory record.

        Expected keys (all optional except title): title, summary, content,
        tags, importance, pinned, source.

        Returns the created view dict, or None on failure.
        """
        title = (memory.get("title") or "").strip()
        if not title:
            logger.warning("MemoryService.add: title required")
            return None
        context = {
            "title": title,
            "summary": memory.get("summary", ""),
            "content": memory.get("content", ""),
            "tags": memory.get("tags", []),
            "importance": memory.get("importance", 0),
            "source": memory.get("source", "ui"),
            "pinned": bool(memory.get("pinned", False)),
        }
        record_id = self._memory.store(
            memory_type="semantic",
            key=f"ui-{int(time.time())}-{title.lower().replace(' ', '-')[:40]}",
            value={"title": title, "summary": context["summary"]},
            context=context,
        )
        view = self.recall(record_id)
        if view:
            self._emit(EventType.MEMORY_CREATED, {"record": view})
        return view

    def update(self, memory: Dict[str, Any]) -> bool:
        """Update an existing record's metadata.

        memory['id'] identifies the record; remaining keys are merged into
        its context. Returns True on success.
        """
        record_id = memory.get("id")
        if not record_id:
            return False
        existing = self._memory.get(record_id)
        if not existing:
            return False
        ctx = dict(existing.context or {})
        for field in ("title", "summary", "content", "tags", "importance", "source", "pinned"):
            if field in memory:
                ctx[field] = memory[field]
        ok = self._memory.update(record_id, context=ctx)
        if ok:
            view = self.recall(record_id)
            self._emit(EventType.MEMORY_UPDATED, {"id": record_id, "record": view})
        return ok

    def delete(self, record_id: str) -> bool:
        """Delete a record by ID. Returns True if deleted."""
        ok = self._memory.delete(record_id)
        if ok:
            self._emit(EventType.MEMORY_DELETED, {"id": record_id})
        return ok

    def set_pinned(self, record_id: str, pinned: bool) -> bool:
        """Pin/unpin a record. Returns True on success."""
        ok = self._memory.set_pinned(record_id, pinned)
        if ok:
            self._emit(
                EventType.MEMORY_PINNED if pinned else EventType.MEMORY_UNPINNED,
                {"id": record_id},
            )
        return ok

    def stats(self) -> Dict[str, Any]:
        """Storage statistics for the UI."""
        return {
            "semantic": self._memory.count("semantic"),
            "episodic": self._memory.count("episodic"),
            "spatial": self._memory.count("spatial"),
            "working": self._memory.count("working"),
            "pinned": len(self.pinned()),
            "total": self._memory.count(),
        }
