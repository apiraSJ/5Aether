"""
Service Container — the single place every part of Aether looks up shared
services (EventBus, CommandBus, ConfigLoader, future services like Memory or
Vision). Nothing should reach into another module's internals directly;
everything goes through this container.

Supports two registration styles:
    - register_instance: register an already-constructed object.
    - register_factory:  register a callable that builds the object lazily,
      optionally cached as a singleton (default) or built fresh every resolve.
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List

logger = logging.getLogger("Aether.ServiceContainer")


class ServiceNotFoundError(Exception):
    """Raised when resolve() is called for a name that was never registered."""


class ServiceBuildError(Exception):
    """Raised when a registered factory fails to build the service."""


class ServiceNames:
    """Constants for all well-known service names. Use these instead of
    raw strings to avoid typo-related runtime failures."""

    CONFIG = "config"
    EVENT_BUS = "event_bus"
    COMMAND_BUS = "command_bus"
    RESULT_PIPELINE = "result_pipeline"
    PLUGIN_LOADER = "plugin_loader"


class IService(ABC):
    """Abstract base for the service container. Enables test doubles and
    alternative implementations."""

    @abstractmethod
    def register_instance(self, name: str, instance: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def register_factory(self, name: str, factory: Callable[[], Any], singleton: bool = True) -> None:
        raise NotImplementedError

    @abstractmethod
    def resolve(self, name: str) -> Any:
        raise NotImplementedError

    @abstractmethod
    def has(self, name: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def unregister(self, name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def registered_names(self) -> List[str]:
        raise NotImplementedError


class ServiceContainer(IService):
    """Thread-safe registry of named services."""

    def __init__(self) -> None:
        self._instances: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._singleton_flags: Dict[str, bool] = {}
        self._lock = threading.RLock()

    def register_instance(self, name: str, instance: Any) -> None:
        """Register a fully constructed object under `name`."""
        with self._lock:
            self._instances[name] = instance
            self._factories.pop(name, None)
            self._singleton_flags.pop(name, None)
        logger.debug("Registered instance service '%s' (%s)", name, type(instance).__name__)

    def register_factory(self, name: str, factory: Callable[[], Any], singleton: bool = True) -> None:
        """Register a factory callable that builds the service on first resolve."""
        with self._lock:
            self._factories[name] = factory
            self._singleton_flags[name] = singleton
            self._instances.pop(name, None)
        logger.debug("Registered factory service '%s' (singleton=%s)", name, singleton)

    def resolve(self, name: str) -> Any:
        """Return the service registered under `name`.

        Raises ServiceNotFoundError if nothing is registered.
        Raises ServiceBuildError if a factory fails.
        """
        with self._lock:
            if name in self._instances:
                return self._instances[name]

            if name in self._factories:
                factory = self._factories[name]
                is_singleton = self._singleton_flags.get(name, True)
                try:
                    built = factory()
                except Exception as exc:
                    raise ServiceBuildError(
                        f"Factory for service '{name}' raised: {exc}"
                    ) from exc

                if is_singleton:
                    self._instances[name] = built
                return built

            known = sorted(set(self._instances) | set(self._factories)) or ["none"]
            raise ServiceNotFoundError(
                f"No service registered under name '{name}'. "
                f"Known services: {known}"
            )

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._instances or name in self._factories

    def unregister(self, name: str) -> None:
        with self._lock:
            self._instances.pop(name, None)
            self._factories.pop(name, None)
            self._singleton_flags.pop(name, None)

    def registered_names(self) -> List[str]:
        with self._lock:
            return sorted(set(self._instances) | set(self._factories))
