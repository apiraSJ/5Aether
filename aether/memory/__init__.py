"""Aether Memory Core — stores, recalls, and queries memory records.

Architecture:
    Plugin → MemoryManager → MemoryRepository (SQLite/Cache/Cloud)

Tables:
    semantic:    Facts and knowledge (FTS5 indexed)
    episodic:    Timeline events (FTS5 indexed)
    spatial:     Objects with 3D positions (R-Tree indexed)
    working:     Short-term memory (TTL-expiring)
"""

from aether.memory.memory_manager import MemoryManager
from aether.memory.models import (
    MemoryRecord,
    MemoryType,
    QueryFilter,
    RecallResult,
    SpatialRecord,
)
from aether.memory.sqlite_repository import SQLiteRepository

__all__ = [
    "MemoryManager",
    "SQLiteRepository",
    "MemoryRecord",
    "MemoryType",
    "QueryFilter",
    "RecallResult",
    "SpatialRecord",
]
