"""Custom exception handlers and error response formatting for Aether API.

Maps ScheduleService exceptions and FastAPI validation errors to the
standardized error response format defined in the API Contract v1.1.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from aether.task.service import (
    ScheduleError,
    ScheduleValidationError,
    ScheduleNotFoundError,
    ScheduleConflictError,
)


class AetherAPIError(Exception):
    """Base exception for API-layer errors with structured error info."""

    def __init__(
        self,
        error: str,
        message: str,
        detail: str | None = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.error = error
        self.message = message
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)


def _error_response(
    error: str,
    message: str,
    detail: str | None = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> JSONResponse:
    """Build standardized error response per API Contract v1.1."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "message": message,
            "detail": detail,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application."""

    @app.exception_handler(ScheduleValidationError)
    async def schedule_validation_error_handler(
        request: Request, exc: ScheduleValidationError
    ) -> JSONResponse:
        return _error_response(
            error="validation_error",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(ScheduleNotFoundError)
    async def schedule_not_found_error_handler(
        request: Request, exc: ScheduleNotFoundError
    ) -> JSONResponse:
        return _error_response(
            error="not_found",
            message=str(exc),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    @app.exception_handler(ScheduleConflictError)
    async def schedule_conflict_error_handler(
        request: Request, exc: ScheduleConflictError
    ) -> JSONResponse:
        return _error_response(
            error="conflict",
            message=str(exc),
            status_code=status.HTTP_409_CONFLICT,
        )

    @app.exception_handler(ScheduleError)
    async def schedule_error_handler(
        request: Request, exc: ScheduleError
    ) -> JSONResponse:
        # Catch-all for any other ScheduleError subclasses
        return _error_response(
            error="internal_error",
            message="An internal schedule error occurred",
            detail=str(exc),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Map FastAPI's 422 to our 400 validation_error format."""
        # Extract first validation error for user-friendly message
        errors = exc.errors()
        if errors:
            first_error = errors[0]
            field = ".".join(str(loc) for loc in first_error["loc"])
            msg = f"{field}: {first_error['msg']}"
        else:
            msg = "Invalid request data"

        return _error_response(
            error="validation_error",
            message=msg,
            detail=str(errors),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_error_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors (e.g., response_model validation)."""
        return _error_response(
            error="validation_error",
            message="Response validation failed",
            detail=str(exc),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @app.exception_handler(AetherAPIError)
    async def aether_api_error_handler(
        request: Request, exc: AetherAPIError
    ) -> JSONResponse:
        return _error_response(
            error=exc.error,
            message=exc.message,
            detail=exc.detail,
            status_code=exc.status_code,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle Starlette HTTPExceptions (including 404 Not Found)."""
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return _error_response(
                error="not_found",
                message="Resource not found",
                detail=exc.detail,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return _error_response(
            error="http_error",
            message=exc.detail,
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all for truly unexpected errors."""
        # Log the full exception for debugging
        import logging
        logging.getLogger("Aether.API").exception("Unhandled exception: %s", exc)

        return _error_response(
            error="internal_error",
            message="An unexpected error occurred",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )