"""MemoryRecord — a single memory entry with temporal context.

SpatialObject describes WHAT and WHERE.
MemoryRecord describes WHEN and WHY it was remembered.

Together they form the persistent spatial memory that satisfies H1:

- SpatialObject: "laptop is on desk"
- MemoryRecord: "user said 'remember laptop on desk' at 2026-07-24T14:30, source=gesture"
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from aether.domain.spatial_object import SpatialObject


@dataclass(frozen=True)
class RecallResult:
    """Result of a memory recall operation.

    Contains the found object, recall quality metrics, and context
    that helped or hindered the recall.

    Design note:
        quality_score is for H1 evaluation (Recall Day 1/3/7 benchmark),
        NOT for memory storage. The RecallEvaluator will compute this;
        MemoryService just carries it along.
    """

    found: bool
    object: Optional[SpatialObject] = None
    alternatives: List[SpatialObject] = field(default_factory=list)
    recall_latency_ms: float = 0.0
    quality_score: float = 0.0  # computed by RecallEvaluator
    query: str = ""
    context_used: bool = False
    reason: str = ""  # why found/not found


@dataclass(frozen=True)
class MemoryRecord:
    """A memory entry linking a SpatialObject to its temporal context.

    Example:
        record = MemoryRecord(
            object=laptop_object,
            source="gesture",
            intent="user wants to track laptop position",
        )
    """

    id: str = field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:8]}")
    object: SpatialObject = field(default_factory=SpatialObject)
    source: str = "unknown"  # "gesture" | "voice" | "keyboard" | "perception"
    intent: str = ""  # why this was remembered
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None  # None = never expires
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def access(self) -> MemoryRecord:
        """Return new record with incremented access count.

        Since the dataclass is frozen, we create a new instance.
        """
        return MemoryRecord(
            id=self.id,
            object=self.object,
            source=self.source,
            intent=self.intent,
            created_at=self.created_at,
            updated_at=datetime.now(),
            expires_at=self.expires_at,
            access_count=self.access_count + 1,
            last_accessed=datetime.now(),
            tags=list(self.tags),
            metadata=dict(self.metadata),
        )

    @property
    def is_expired(self) -> bool:
        """Check if this memory has expired."""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at

    @property
    def age_days(self) -> float:
        """Age of this memory in days."""
        delta = datetime.now() - self.created_at
        return delta.total_seconds() / 86400.0

    @property
    def days_since_access(self) -> float:
        """Days since this memory was last accessed."""
        if self.last_accessed is None:
            return self.age_days
        delta = datetime.now() - self.last_accessed
        return delta.total_seconds() / 86400.0
