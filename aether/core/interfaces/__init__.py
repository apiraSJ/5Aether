"""Aether Core Interfaces — the contracts of the system.

Every service in Aether communicates through these interfaces.
Implementations live in aether/infrastructure/ or specific plugins.

Rule: Interfaces belong to the core. Implementations belong to infrastructure.
"""

from aether.core.interfaces.i_memory_repository import (
    IMemoryRepository,
    ISpatialRepository,
    ITaskRepository,
    IContextRepository,
    IHistoryRepository,
)
from aether.core.interfaces.i_memory_service import IMemoryService
from aether.core.interfaces.i_reasoning_service import IReasoningService
from aether.core.interfaces.i_context_provider import IContextProvider

__all__ = [
    "IMemoryRepository",
    "ISpatialRepository",
    "ITaskRepository",
    "IContextRepository",
    "IHistoryRepository",
    "IMemoryService",
    "IReasoningService",
    "IContextProvider",
]
