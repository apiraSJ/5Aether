"""Service layer — shared application services.

Architecture:
    Widget/Controller → Service → MemoryManager → SQLiteRepository
"""

from aether.services.memory_service import MemoryService

__all__ = ["MemoryService"]
