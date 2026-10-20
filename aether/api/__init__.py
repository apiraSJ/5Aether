"""Aether Mark-1 Track B — FastAPI Web API for Task & Calendar Assistant.

This module provides the FastAPI application factory and exports the
public API surface for the Web track (Track B).

The API is a thin adapter over the existing ScheduleService (Track A),
exposing Task/Event CRUD and Calendar queries via REST endpoints.
"""

from .main import create_app

__all__ = ["create_app"]