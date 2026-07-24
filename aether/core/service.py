"""
IService — lifecycle contract for all domain services.

Every service in the Aether architecture implements this three-phase lifecycle.
The Application calls these at the appropriate times; services never call each other directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class IService(ABC):
    """Base interface for all domain services (Memory, Reasoning, Context, etc.)."""

    @abstractmethod
    def start(self) -> None:
        """Called once after all services are constructed and registered.
        Use for: opening connections, loading models, starting background threads.
        Must not call other services' methods.
        """
        ...

    @abstractmethod
    def update(self, dt: float) -> None:
        """Called every application tick with delta time in seconds.
        Use for: time-based expiration, periodic cleanup, animation, prediction.
        Must be fast and non-blocking.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Called once during application shutdown (reverse order of start).
        Use for: closing connections, saving state, stopping threads.
        Must not call other services' methods.
        """
        ...