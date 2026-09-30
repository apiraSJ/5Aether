"""MemoryManager — public API for all memory operations.

Architecture:
    Plugin/Service → MemoryManager → MemoryRepository (SQLite/Cache/Cloud)

All memory access goes through this manager. No direct repository access.
Events published on EventBus for Scene Graph, Planner, GUI to subscribe.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from aether.memory.models import (
    MemoryRecord,
    MemoryType,
    QueryFilter,
    RecallResult,
    SpatialRecord,
)
from aether.memory.sqlite_repository import SQLiteRepository

logger = logging.getLogger("Aether.MemoryManager")


class MemoryManager:
    """Public API for memory operations.

    Usage:
        memory = MemoryManager(db_path="data/memory.db")
        memory.open()

        # Store a fact
        memory.store("semantic", "bottle", {"location": "desk", "color": "blue"})

        # Recall a fact
        result = memory.recall("bottle")
        if result.found:
            print(result.records[0].value)

        # Full-text search
        result = memory.search("blue bottle")

        # Spatial query
        result = memory.recall_nearby(x=1.0, y=2.0, z=0.0, radius=5.0)

        # Forget
        memory.forget("bottle")

        memory.close()
    """

    def __init__(
        self,
        db_path: str = "data/memory.db",
        event_bus=None,
    ) -> None:
        self._repository = SQLiteRepository(db_path)
        self._event_bus = event_bus
        self._open = False

    def open(self) -> None:
        """Open database connection."""
        self._repository.open()
        self._open = True
        logger.info("MemoryManager ready")

    def close(self) -> None:
        """Close database connection."""
        if self._open:
            self._repository.close()
            self._open = False
            logger.info("MemoryManager closed")

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def repository(self) -> SQLiteRepository:
        """Expose repository for direct queries (internal use only)."""
        return self._repository

    # ── Public API ─────────────────────────────────────────────────

    def store(
        self,
        memory_type: str,
        key: str,
        value: Any = None,
        context: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        confidence: float = 1.0,
        label: str = "",
    ) -> str:
        """Store a memory record.

        Args:
            memory_type: "semantic", "episodic", "spatial", or "working"
            key: Primary lookup key
            value: JSON-serializable payload
            context: Optional metadata (confidence, source, tags)
            ttl_seconds: Time-to-live (None = infinite)
            x, y, z: 3D position (spatial only)
            confidence: Detection confidence (spatial only)
            label: Object label (spatial only)

        Returns:
            Record ID (UUID string)
        """
        mtype = self._parse_type(memory_type)
        record_id = self._repository.store(
            memory_type=mtype,
            key=key,
            value=value,
            context=context,
            ttl_seconds=ttl_seconds,
            x=x,
            y=y,
            z=z,
            confidence=confidence,
            label=label,
        )

        self._emit(f"memory.{mtype.value}.created", {
            "id": record_id,
            "key": key,
            "memory_type": mtype.value,
            "value": value,
        })

        return record_id

    def recall(self, key: str, memory_type: Optional[str] = None) -> RecallResult:
        """Recall a memory record by key.

        Args:
            key: Primary lookup key
            memory_type: Optional type filter ("semantic", "episodic", etc.)

        Returns:
            RecallResult with matching records
        """
        mtype = self._parse_type(memory_type) if memory_type else None
        result = self._repository.recall(key, mtype)

        if result.found:
            self._emit("memory.queried", {
                "key": key,
                "memory_type": memory_type or "all",
                "found": True,
                "count": result.total,
            })

        return result

    def search(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 20,
    ) -> RecallResult:
        """Full-text search across semantic and episodic memory.

        Uses FTS5 for fast text matching.

        Args:
            query: Search text
            memory_type: Optional type filter
            limit: Maximum results

        Returns:
            RecallResult with matching records
        """
        filter_obj = QueryFilter(
            memory_type=memory_type,
            limit=limit,
        )
        result = self._repository.search(query, filter_obj)

        self._emit("memory.query.completed", {
            "query": query,
            "found": result.found,
            "count": result.total,
            "time_ms": result.query_time_ms,
        })

        return result

    def recall_nearby(
        self,
        x: float,
        y: float,
        z: float,
        radius_meters: float = 5.0,
        label: Optional[str] = None,
        limit: int = 20,
    ) -> RecallResult:
        """Find spatial records near a 3D position.

        Uses R-Tree index for efficient spatial queries.

        Args:
            x, y, z: Query position
            radius_meters: Search radius
            label: Optional object label filter
            limit: Maximum results

        Returns:
            RecallResult with SpatialRecords
        """
        result = self._repository.recall_nearby(x, y, z, radius_meters, label, limit)

        self._emit("memory.spatial.queried", {
            "x": x, "y": y, "z": z,
            "radius": radius_meters,
            "found": result.found,
            "count": result.total,
            "label": label,
        })

        return result

    def update(
        self,
        record_id: str,
        value: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update a memory record by ID.

        Args:
            record_id: Record UUID
            value: New value (None = keep existing)
            context: New context (None = keep existing)

        Returns:
            True if record was found and updated
        """
        success = self._repository.update(record_id, value, context)

        if success:
            self._emit("memory.updated", {
                "id": record_id,
            })

        return success

    def forget(self, key: str, memory_type: Optional[str] = None) -> int:
        """Delete memory records by key.

        Args:
            key: Primary lookup key
            memory_type: Optional type filter

        Returns:
            Number of records deleted
        """
        mtype = self._parse_type(memory_type) if memory_type else None
        count = self._repository.forget(key, mtype)

        if count > 0:
            self._emit(f"memory.deleted", {
                "key": key,
                "memory_type": memory_type or "all",
                "count": count,
            })

        return count

    def expire_stale(self) -> int:
        """Delete all expired records based on TTL.

        Returns:
            Number of records deleted
        """
        return self._repository.expire_stale()

    def count(self, memory_type: Optional[str] = None) -> int:
        """Count records in memory store.

        Args:
            memory_type: Optional type filter

        Returns:
            Number of records
        """
        mtype = self._parse_type(memory_type) if memory_type else None
        return self._repository.count(mtype)

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        """Fetch a single record by ID across all memory tables."""
        return self._repository.get(record_id)

    def delete(self, record_id: str) -> bool:
        """Delete a single record by ID. Returns True if found and deleted.

        Emits a memory.deleted event when a record is removed.
        """
        deleted = self._repository.delete(record_id)
        if deleted:
            self._emit("memory.deleted", {
                "id": record_id,
                "count": 1,
            })
        return deleted

    def list_recent(
        self,
        limit: int = 10,
        memory_type: Optional[str] = None,
    ) -> RecallResult:
        """List the most recently updated records (semantic + episodic).

        Args:
            limit: Maximum number of records
            memory_type: Optional type filter

        Returns:
            RecallResult ordered by updated_at DESC
        """
        mtype = self._parse_type(memory_type) if memory_type else None
        return self._repository.list_recent(limit=limit, memory_type=mtype)

    def list_pinned(
        self,
        limit: int = 20,
        memory_type: Optional[str] = None,
    ) -> RecallResult:
        """List pinned records (context['pinned'] == true).

        Args:
            limit: Maximum number of records
            memory_type: Optional type filter

        Returns:
            RecallResult ordered by updated_at DESC
        """
        mtype = self._parse_type(memory_type) if memory_type else None
        return self._repository.list_pinned(limit=limit, memory_type=mtype)

    def set_pinned(self, record_id: str, pinned: bool) -> bool:
        """Set the pinned flag on a record. Returns True if found and updated.

        Emits a memory.pinned / memory.unpinned event.
        """
        success = self._repository.set_pinned(record_id, pinned)
        if success:
            self._emit("memory.pinned" if pinned else "memory.unpinned", {
                "id": record_id,
            })
        return success

    def seed_if_empty(self) -> int:
        """Seed the store with demo records on first boot.

        Architecture:
            MemoryManager.seed_if_empty() → repository.seed_demo()

        Seeds only when the store is completely empty (no semantic records).
        After the user stores their own semantic memory, this never fires again.

        Returns:
            Number of records seeded (0 if the store was already populated)
        """
        semantic_count = self._repository.count(MemoryType.SEMANTIC)
        if semantic_count > 0:
            return 0

        from aether.memory.seed_data import DEMO_MEMORIES

        seeded = self._repository.seed_demo(DEMO_MEMORIES)
        if seeded:
            logger.info("Seeded %d demo memory records", seeded)
        return seeded

    def list_keys(self, memory_type: Optional[str] = None) -> List[str]:
        """List all unique keys in memory store.

        Args:
            memory_type: Optional type filter

        Returns:
            Sorted list of unique keys
        """
        mtype = self._parse_type(memory_type) if memory_type else None
        return self._repository.list_keys(mtype)

    # ── Internal ───────────────────────────────────────────────────

    def _parse_type(self, type_name: str) -> MemoryType:
        """Parse string to MemoryType enum."""
        normalized = type_name.lower().strip()
        for mt in MemoryType:
            if mt.value == normalized:
                return mt
        raise ValueError(f"Unknown memory type: {type_name}")

    def _emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        """Emit an event on EventBus."""
        if self._event_bus:
            try:
                from aether.core.event_bus_v2 import Event
                self._event_bus.publish(Event(type=event_name, payload=payload))
            except Exception as e:
                logger.warning("Failed to emit event %s: %s", event_name, e)
