"""Simple in-memory memory service for Phase B demonstration.

Implements IService lifecycle. Stores spatial objects and facts in memory.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from aether.core.service import IService

logger = logging.getLogger("Aether.MemoryService")


class MemoryService(IService):
    """In-memory key-value store for spatial objects and facts.

    Phase B: Simple dict-based storage. Phase D: swap to SQLite + ChromaDB
    without changing AetherApplication.
    """

    def __init__(self) -> None:
        self._objects: Dict[str, Dict[str, Any]] = {}  # object_id -> spatial data
        self._facts: Dict[str, List[Dict[str, Any]]] = {}  # key -> list of fact records
        self._started = False

    # --- IService lifecycle ---

    def start(self) -> None:
        """Initialize the service."""
        if self._started:
            return
        logger.info("MemoryService starting...")
        self._objects.clear()
        self._facts.clear()
        self._started = True
        logger.info("MemoryService started")

    def update(self, dt: float) -> None:
        """Per-tick maintenance: cleanup expired facts, etc."""
        if not self._started:
            return
        # Could add TTL cleanup here in future

    def stop(self) -> None:
        """Persist state (Phase B: no-op, Phase D: write to disk)."""
        if not self._started:
            return
        logger.info("MemoryService stopping... (%d objects, %d fact keys)",
                    len(self._objects), len(self._facts))
        self._started = False

    # --- Domain API (called by handlers) ---

    def remember_object(self, object_id: str, data: Dict[str, Any]) -> None:
        """Store or update a spatial object."""
        self._objects[object_id] = {"id": object_id, **data}
        logger.debug("Remembered object: %s", object_id)

    def recall_object(self, object_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a spatial object by ID."""
        return self._objects.get(object_id)

    def forget_object(self, object_id: str) -> bool:
        """Remove a spatial object. Returns True if existed."""
        if object_id in self._objects:
            del self._objects[object_id]
            logger.debug("Forgot object: %s", object_id)
            return True
        return False

    def list_objects(self) -> List[Dict[str, Any]]:
        """Return all stored objects."""
        return list(self._objects.values())

    def remember_fact(self, key: str, fact: Dict[str, Any]) -> None:
        """Append a fact to a key's fact list."""
        self._facts.setdefault(key, []).append(fact)
        logger.debug("Remembered fact for key: %s", key)

    def recall_facts(self, key: str) -> List[Dict[str, Any]]:
        """Get all facts for a key."""
        return self._facts.get(key, [])

    def clear_facts(self, key: str) -> int:
        """Clear all facts for a key. Returns count cleared."""
        count = len(self._facts.get(key, []))
        if key in self._facts:
            del self._facts[key]
        logger.debug("Cleared %d facts for key: %s", count, key)
        return count

    def get_stats(self) -> Dict[str, int]:
        """Return storage statistics."""
        return {
            "objects": len(self._objects),
            "fact_keys": len(self._facts),
            "total_facts": sum(len(v) for v in self._facts.values()),
        }