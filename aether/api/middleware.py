"""Middleware for Aether API security and request processing.

Implements local-only access control per API Contract v1.1:
- Validates Host header is localhost/127.0.0.1
- Enforces local-only access boundary
"""

from __future__ import annotations

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


ALLOWED_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce local-only access per API Contract v1.1.

    Validates:
    - Host header is localhost/127.0.0.1
    - Rejects requests from non-local hosts with 403
    """

    async def dispatch(self, request, call_next):
        # Skip validation for health endpoint (optional, but allows probes)
        if request.url.path == "/health":
            return await call_next(request)

        host_header = request.headers.get("host", "")
        # Extract host without port
        host = host_header.split(":")[0].lower()

        if host not in ALLOWED_HOSTS:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "error": "forbidden",
                    "message": f"Access denied: host '{host}' not allowed. API is local-only.",
                },
            )

        return await call_next(request)


def add_security_middleware(app) -> None:
    """Add security middleware to FastAPI application."""
    app.add_middleware(LocalOnlyMiddleware)