"""FastAPI application factory for Aether Mark-1 Track B Web API.

Creates and configures the FastAPI application with:
- API prefix /api/v1
- Exception handlers (ScheduleService errors + validation errors)
- Security middleware (local-only access)
- Route registration (tasks, calendar)
- Health endpoint
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from aether.api.errors import register_exception_handlers
from aether.api.middleware import add_security_middleware
from aether.api.routes import calendar, tasks
from aether.api.schemas import HealthResponse
from aether.core.service_container import ServiceContainer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    The Aether ServiceContainer and ScheduleService are initialized
    by the host application (AetherApp) and attached to app.state.
    This lifespan just ensures clean shutdown.
    """
    # Startup: nothing to do here - container is set by host
    yield
    # Shutdown: nothing to do here - host handles shutdown


def create_app(
    container: Optional["ServiceContainer"] = None,
    *,
    title: str = "Aether Mark-1 API",
    version: str = "1.0.0",
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        container: Optional Aether ServiceContainer with registered
            ScheduleService ("schedule_service"). If provided, attached
            to app.state for dependency injection.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="Aether Mark-1 API",
        version="1.0.0",
        description="Web API for Aether Mark-1 Task & Calendar Assistant (Track B)",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Store container in app.state for dependency injection
    if container is not None:
        app.state.container = container

    # Register exception handlers (ScheduleService + validation)
    register_exception_handlers(app)

    # Add security middleware (local-only access)
    from aether.api.middleware import add_security_middleware

    add_security_middleware(app)

    # Include routers with /api/v1 prefix
    app.include_router(tasks.router, prefix="/api/v1")
    app.include_router(calendar.router, prefix="/api/v1")

    # Health check endpoint (no auth, no host validation)
    @app.get("/health", response_model=None, include_in_schema=False)
    async def health_check() -> dict:
        return {"status": "ok", "service": "aether-api", "version": "1.0.0"}

    # Root endpoint
    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "service": "aether-api",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/health",
        }

    return app