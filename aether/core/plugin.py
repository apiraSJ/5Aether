"""Plugin system — input adapters that produce Commands.

Plugins NEVER contain domain logic. They translate external input
(keyboard, camera, XR, network) into Commands on the CommandBus.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Protocol

from aether.core.service_container import ServiceContainer


@dataclass(frozen=True)
class PluginMetadata:
    """Declarative metadata for a plugin. Single source of truth for help, command palette, dashboard."""

    label: str
    version: str = "1.0"
    category: str = "general"
    commands: List[str] = field(default_factory=list)
    description: str = ""


class PluginBase(ABC):
    """Base contract — all plugins must implement.

    initialize(): called once during boot, receives DI container
    shutdown(): called once during app shutdown
    metadata(): declarative info for help, command palette, dashboard
    """

    name: str = ""  # Required class attribute, validated at import time
    _metadata: Optional[PluginMetadata] = None

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Skip validation for abstract base classes
        if cls.__name__ in ("PluginBase", "TickablePlugin"):
            return
        if not getattr(cls, "name", ""):
            raise TypeError(f"Plugin class '{cls.__name__}' must define a 'name' class attribute")

    @property
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata. Override in subclass to declare commands, version, etc."""
        if self._metadata is None:
            self._metadata = PluginMetadata(label=self.name)
        return self._metadata

    @abstractmethod
    def initialize(self, container: ServiceContainer) -> None:
        """Resolve dependencies from container. Register commands, subscribe to events.
        Raise on failure — PluginLoader will report and optionally abort boot.
        """
        raise NotImplementedError

    def shutdown(self) -> None:
        """Release resources: threads, handles, model instances, file descriptors."""
        pass


class TickablePlugin(PluginBase):
    """Plugin that participates in the Application tick loop.

    Subclass this when your plugin needs to poll input each frame
    (keyboard, camera, XR controller, network socket).
    """

    name = ""  # Abstract base class - concrete subclasses must override

    def start(self) -> None:
        """Called once after all plugins initialized. Start capture threads, connect devices."""
        pass

    @abstractmethod
    def update(self, dt: float) -> None:
        """Called every Application tick. dt = seconds since last tick.
        Read input → emit Command(s) via CommandBus.
        """
        raise NotImplementedError

    def stop(self) -> None:
        """Called once before shutdown. Stop threads, disconnect devices."""
        pass


class IPlugin(Protocol):
    """Structural protocol for type-checking."""

    name: str

    def initialize(self, container: ServiceContainer) -> None: ...

    def shutdown(self) -> None: ...


class ITickablePlugin(IPlugin, Protocol):
    """Protocol for plugins that receive tick updates."""

    def start(self) -> None: ...

    def update(self, dt: float) -> None: ...

    def stop(self) -> None: ...