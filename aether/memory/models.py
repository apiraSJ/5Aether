"""Memory domain models for Aether Memory Core.

Architecture:
    MemoryManager → MemoryRepository → SQLite/Cache

All domain models are frozen dataclasses for immutability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class MemoryType(Enum):
    """Type of memory storage."""
    WORKING = "working"
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    SPATIAL = "spatial"


@dataclass(frozen=True)
class MemoryRecord:
    """Single memory record stored in any memory table.

    Fields:
        id: Unique identifier (UUID string)
        memory_type: Type of memory (semantic, episodic, spatial, working)
        key: Primary lookup key (e.g., object name, event ID)
        value: Arbitrary JSON-serializable payload
        context: Optional metadata dict (confidence, source, tags, etc.)
        created_at: Record creation timestamp
        updated_at: Last update timestamp
        access_count: Number of times this record was recalled
        ttl_seconds: Time-to-live in seconds (None = infinite)
    """
    id: str
    memory_type: str
    key: str
    value: Any = None
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    access_count: int = 0
    ttl_seconds: Optional[float] = None

    @property
    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        age = datetime.now().timestamp() - self.created_at
        return age > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        return datetime.now().timestamp() - self.created_at


@dataclass(frozen=True)
class SpatialRecord(MemoryRecord):
    """Spatial memory record with position.

    Fields:
        x, y, z: 3D position coordinates
        confidence: Detection confidence (0.0–1.0)
        label: Object label/class name
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    confidence: float = 0.0
    label: str = ""


@dataclass(frozen=True)
class RecallResult:
    """Result of a memory recall query."""
    found: bool = False
    records: List[MemoryRecord] = field(default_factory=list)
    total: int = 0
    query_time_ms: float = 0.0
    error: Optional[str] = None

    @classmethod
    def not_found(cls, query_time_ms: float = 0.0) -> "RecallResult":
        return cls(found=False, query_time_ms=query_time_ms)

    @classmethod
    def error_result(cls, error: str) -> "RecallResult":
        return cls(found=False, error=error)


@dataclass(frozen=True)
class QueryFilter:
    """Filter for memory queries."""
    memory_type: Optional[str] = None
    key_pattern: Optional[str] = None  # FTS5 search pattern
    min_confidence: Optional[float] = None
    max_age_seconds: Optional[float] = None
    tags: Optional[List[str]] = None
    limit: int = 20
    offset: int = 0
    order_by: str = "updated_at DESC"

    # Spatial filters
    near_x: Optional[float] = None
    near_y: Optional[float] = None
    near_z: Optional[float] = None
    radius_meters: Optional[float] = None
