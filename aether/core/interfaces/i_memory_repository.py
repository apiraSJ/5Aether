"""IMemoryRepository — persistence contracts for all data types.

This is the L2 boundary: everything below is storage (JSON, SQLite, VectorDB).
Everything above is domain logic.

Sub-interfaces split by data type to enforce SRP:
    ISpatialRepository  — spatial objects + relations
    ITaskRepository     — task lifecycle
    IContextRepository  — context snapshots
    IHistoryRepository  — append-only event/action log

Implementations:
    JsonMemoryRepository    — development / testing
    SQLiteMemoryRepository — production
    VectorMemoryRepository — future (semantic search)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from aether.domain.spatial_object import SpatialObject
from aether.domain.memory_record import MemoryRecord
from aether.domain.task import Task
from aether.domain.context_snapshot import ContextSnapshot


class ISpatialRepository(ABC):
    """CRUD for spatial objects with relation queries."""

    @abstractmethod
    def save(self, obj: SpatialObject) -> bool:
        """Save or update a spatial object."""
        ...

    @abstractmethod
    def find_by_id(self, obj_id: str) -> Optional[SpatialObject]:
        """Find a spatial object by its ID."""
        ...

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[SpatialObject]:
        """Find a spatial object by name (first match)."""
        ...

    @abstractmethod
    def find_all(self, tag: Optional[str] = None) -> List[SpatialObject]:
        """Find all objects, optionally filtered by tag."""
        ...

    @abstractmethod
    def find_near(self, name: str, radius: float = 1.0) -> List[SpatialObject]:
        """Find objects near a named object within radius (meters)."""
        ...

    @abstractmethod
    def find_by_relation(
        self, relation_type: str, target_id: str
    ) -> List[SpatialObject]:
        """Find all objects that have a specific relation to target."""
        ...

    @abstractmethod
    def delete(self, obj_id: str) -> bool:
        """Delete a spatial object by ID."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Return total number of spatial objects."""
        ...


class ITaskRepository(ABC):
    """CRUD for task lifecycle."""

    @abstractmethod
    def save(self, task: Task) -> bool:
        """Save or update a task."""
        ...

    @abstractmethod
    def find_by_id(self, task_id: str) -> Optional[Task]:
        """Find a task by ID."""
        ...

    @abstractmethod
    def find_by_status(self, status: str) -> List[Task]:
        """Find tasks by status (pending, running, completed, cancelled)."""
        ...

    @abstractmethod
    def find_all(self) -> List[Task]:
        """Find all tasks."""
        ...

    @abstractmethod
    def delete(self, task_id: str) -> bool:
        """Delete a task by ID."""
        ...


class IContextRepository(ABC):
    """Persistence for context snapshots (current + recent history)."""

    @abstractmethod
    def save(self, snapshot: ContextSnapshot) -> bool:
        """Save a context snapshot (replaces current)."""
        ...

    @abstractmethod
    def get_current(self) -> Optional[ContextSnapshot]:
        """Get the most recent context snapshot."""
        ...

    @abstractmethod
    def get_history(self, limit: int = 10) -> List[ContextSnapshot]:
        """Get recent context history."""
        ...


class IHistoryRepository(ABC):
    """Append-only log of memory operations for audit + evaluation."""

    @abstractmethod
    def append(self, record: MemoryRecord) -> bool:
        """Append a memory record to history."""
        ...

    @abstractmethod
    def find_by_object(self, object_id: str) -> List[MemoryRecord]:
        """Find all memory records for an object."""
        ...

    @abstractmethod
    def find_recent(self, limit: int = 50) -> List[MemoryRecord]:
        """Find most recent memory records."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Total number of history records."""
        ...


class IMemoryRepository(ABC):
    """Composite repository — groups all sub-repositories.

    This is the single entry point for infrastructure implementations.
    A JSON adapter implements all four; a SQLite adapter implements all four.

    Example:
        repo = JsonMemoryRepository(base_path="data/")
        repo.spatial.save(laptop_object)
        repo.tasks.save(task)
        records = repo.history.find_recent(limit=10)
    """

    @property
    @abstractmethod
    def spatial(self) -> ISpatialRepository:
        """Spatial object repository."""
        ...

    @property
    @abstractmethod
    def tasks(self) -> ITaskRepository:
        """Task repository."""
        ...

    @property
    @abstractmethod
    def context(self) -> IContextRepository:
        """Context repository."""
        ...

    @property
    @abstractmethod
    def history(self) -> IHistoryRepository:
        """History repository."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release resources (file handles, connections)."""
        ...
