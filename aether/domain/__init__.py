"""Aether Domain Models — the language of the system.

These are NOT data-access objects. They are the contracts that flow
between services. Interfaces reference domain models; implementations
serialize/deserialize them to JSON, SQLite, or any future backend.

Rule: Domain models belong to the domain, interfaces belong to the core,
implementations belong to infrastructure.
"""

from aether.domain.spatial_object import SpatialObject, SpatialRelation
from aether.domain.memory_record import MemoryRecord, RecallResult
from aether.domain.context_snapshot import ContextSnapshot, InteractionMode
from aether.domain.task import Task, TaskStatus

__all__ = [
    "SpatialObject",
    "SpatialRelation",
    "MemoryRecord",
    "RecallResult",
    "ContextSnapshot",
    "InteractionMode",
    "Task",
    "TaskStatus",
]
