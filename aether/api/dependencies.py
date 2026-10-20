"""FastAPI dependency injection for Aether API.

Provides access to the ScheduleService instance from the Aether container.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from aether.core.service_container import ServiceContainer
from aether.task.service import ScheduleService


def get_service_container(request: Request) -> ServiceContainer:
    """Get the Aether ServiceContainer from the app state.

    The container is stored in app.state.container during startup.
    """
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(
            status_code=503,
            detail="Service container not initialized",
        )
    return container


def get_schedule_service(
    container: ServiceContainer = Depends(get_service_container),
) -> ScheduleService:
    """Get the ScheduleService instance from the container.

    The TaskPlugin registers the ScheduleService as "schedule_service"
    during initialization.
    """
    if not container.has("schedule_service"):
        raise HTTPException(
            status_code=503,
            detail="ScheduleService not available",
        )
    return container.resolve("schedule_service")