"""IMemoryService — the L3 contract for memory operations.

This is NOT a repository. It is a service that:
    1. Receives recall/remember/forget commands
    2. Delegates to IMemoryRepository for storage
    3. Adds temporal context, access tracking, and query enrichment
    4. Returns domain results (RecallResult, not raw data)

Design:
    MemoryService does NOT reason. It remembers and recalls.
    ReasoningService does NOT store. It interprets memory.

    MemoryService
        ↓
    RecallResult

    ReasoningService
        ↓
    Answer (from RecallResult + Context)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from aether.domain.spatial_object import SpatialObject
from aether.domain.memory_record import MemoryRecord, RecallResult
from aether.domain.context_snapshot import ContextSnapshot


class IMemoryService(ABC):
    """High-level memory operations with temporal context."""

    @abstractmethod
    def remember(
        self,
        obj: SpatialObject,
        source: str = "unknown",
        intent: str = "",
    ) -> MemoryRecord:
        """Remember a spatial object.

        Args:
            obj: The spatial object to remember
            source: How it was remembered (gesture, voice, keyboard, perception)
            intent: Why it was remembered

        Returns:
            MemoryRecord with temporal metadata
        """
        ...

    @abstractmethod
    def recall(
        self,
        query: str,
        context: Optional[ContextSnapshot] = None,
    ) -> RecallResult:
        """Recall a spatial object by name or description.

        Uses context to disambiguate (e.g., "laptop" in developer mode
        might refer to a different laptop than in normal mode).

        Args:
            query: Name or description to search for
            context: Current context for disambiguation

        Returns:
            RecallResult with found object + quality metrics
        """
        ...

    @abstractmethod
    def forget(self, name: str) -> bool:
        """Remove a spatial object from memory.

        Returns True if object was found and removed.
        """
        ...

    @abstractmethod
    def associate(
        self,
        source_name: str,
        relation_type: str,
        target_name: str,
    ) -> bool:
        """Create a spatial relation between two objects.

        Example: associate("laptop", "left_of", "charger")

        Returns True if both objects exist and relation was created.
        """
        ...

    @abstractmethod
    def find_all(self, tag: Optional[str] = None) -> List[SpatialObject]:
        """Find all remembered objects, optionally filtered by tag."""
        ...

    @abstractmethod
    def recall_history(self, object_id: str) -> List[MemoryRecord]:
        """Get the access history of an object.

        Used by RecallEvaluator to compute recall quality metrics.
        """
        ...

    @abstractmethod
    def object_count(self) -> int:
        """Total number of objects in memory."""
        ...
