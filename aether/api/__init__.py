"""Aether Mark-1 Track B — FastAPI Web API for Task & Calendar Assistant.

This module provides the FastAPI application factory and exports the
public API surface for the Web track (Track B).

The API is a thin adapter over the existing ScheduleService (Track A),
exposing Task/Event CRUD and Calendar queries via REST endpoints.

``create_app`` is resolved lazily: importing ``aether.api`` (and therefore
``aether.api.server``) must not require FastAPI itself. ``--mode web``
boots the application first; when the running interpreter lacks the
``[server]`` extra, ``server.run()`` reports an actionable install hint
instead of the import dying here on a raw ModuleNotFoundError traceback.
"""

from typing import Any

__all__ = ["create_app"]


def __getattr__(name: str) -> Any:
    """Expose ``create_app`` on first access (PEP 562 lazy import)."""
    if name == "create_app":
        from .main import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
