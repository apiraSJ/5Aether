"""
IService — base contract for all services in the ADR architecture.

Services contain domain logic and state. They never directly depend on plugins,
UI widgets, or input adapters. Communication happens exclusively through
the EventBus and CommandBus.

Lifecycle:
  1. container.register(IService, instance)  — during boot
  2. service.initialize(container)           — resolve dependencies
  3. service.start()                         — begin accepting work
  4. service.stop()                          — release resources

Services should be stateless where possible. If they hold state, it must be
thread-safe since plugins may call them from different threads.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from aether.core.service_container import ServiceContainer


class IService(ABC):
    """Base interface for all services.

    All services must implement this interface. Services are registered
    in the DI container and resolved by plugins that need them.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable service name for logging and debugging."""
        raise NotImplementedError

    @abstractmethod
    def initialize(self, container: ServiceContainer) -> None:
        """Resolve dependencies from the DI container.

        Called once during boot after all services are registered.
        Services should resolve their dependencies here, NOT in __init__.
        Raise on failure — PluginLoader will report and abort boot.
        """
        raise NotImplementedError

    def start(self) -> None:
        """Start the service (open connections, start background threads).

        Called once after all plugins are initialized.
        Default implementation is a no-op.
        """
        pass

    def stop(self) -> None:
        """Stop the service (close connections, join threads).

        Called once during app shutdown.
        Default implementation is a no-op.
        """
        pass

    def get_status(self) -> dict[str, Any]:
        """Return service status for health checks and dashboard.

        Override in subclass to provide meaningful status info.
        Default implementation returns basic status.
        """
        return {
            "service": self.name,
            "status": "running",
        }


class IStatefulService(IService):
    """Service that maintains persistent state (e.g., MemoryService, TaskService).

    Adds state persistence and recovery capabilities.
    """

    @abstractmethod
    def save_state(self) -> bool:
        """Persist current state to disk/database.

        Returns True on success, False on failure.
        Called during graceful shutdown and periodically.
        """
        raise NotImplementedError

    @abstractmethod
    def load_state(self) -> bool:
        """Load state from disk/database.

        Returns True if state was loaded, False if starting fresh.
        Called during initialization.
        """
        raise NotImplementedError

    def get_state_info(self) -> dict[str, Any]:
        """Return information about current state for debugging.

        Override in subclass to provide state-specific info.
        """
        return {
            "service": self.name,
            "has_state": True,
        }
