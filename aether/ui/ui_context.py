"""UIContext — the single, immutable injection point for the UI layer.

The GUIPlugin builds one UIContext after every shared service is
registered, then hands it to the UIShell and to every widget. Widgets
read from the context; they never mutate it (it is a frozen dataclass)
and never reach into the DI container themselves.

This replaces the old per-widget `wire_services(...)` signatures with a
single bundle, keeping XR/Web/Mobile shells free to build their own
UIContext from the same services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from aether.core.service_container import ServiceContainer


def _optional(container: Optional[ServiceContainer], name: str) -> Any:
    """Resolve a service from the container, returning None if absent."""
    if container is None:
        return None
    try:
        return container.resolve(name) if container.has(name) else None
    except Exception:
        return None


@dataclass(slots=True, frozen=True)
class UIContext:
    """Frozen bundle of shared UI dependencies.

    All fields are optional so widgets can be constructed and tested in
    isolation; the shell fills them from the container via
    ``UIContext.from_container``.
    """

    command_bus: Any = None
    event_bus: Any = None
    container: Optional[ServiceContainer] = None
    config: Any = None
    panel_registry: Any = None
    command_registry: Any = None
    workspace_manager: Any = None
    memory_service: Any = None
    notification_manager: Any = None
    overlay_model: Any = None
    overlay_controller: Any = None
    hud_manager: Any = None
    ai_worker: Any = None

    @classmethod
    def from_container(
        cls,
        container: ServiceContainer,
        *,
        overlay_model: Any = None,
        overlay_controller: Any = None,
        hud_manager: Any = None,
    ) -> "UIContext":
        """Build a context by resolving the known services from a container."""
        return cls(
            command_bus=_optional(container, "command_bus"),
            event_bus=_optional(container, "event_bus"),
            container=container,
            config=_optional(container, "config"),
            panel_registry=_optional(container, "panel_registry"),
            command_registry=_optional(container, "command_registry"),
            workspace_manager=_optional(container, "workspace_manager"),
            memory_service=_optional(container, "memory_service"),
            notification_manager=_optional(container, "notification_manager"),
            ai_worker=_optional(container, "ai_worker"),
            overlay_model=overlay_model,
            overlay_controller=overlay_controller,
            hud_manager=hud_manager,
        )
