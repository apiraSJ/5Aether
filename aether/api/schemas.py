"""Pydantic schemas for Aether API request/response validation.

Defines the data models per API Contract v1.1 for request/response
validation and serialization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskItemBase(BaseModel):
    """Base fields for a Task/Event item."""

    kind: str = Field(pattern="^(task|event)$")
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    due_date: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    all_day: bool = False
    tz: str = "Asia/Bangkok"
    owner: Optional[str] = None
    source: str = "manual"

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in ("task", "event"):
            raise ValueError("kind must be 'task' or 'event'")
        return v

    @field_validator("tz")
    @classmethod
    def validate_tz(cls, v: str) -> str:
        # Only support the two timezones in the registry
        if v not in ("Asia/Bangkok", "UTC"):
            raise ValueError("Unsupported timezone. Supported: Asia/Bangkok, UTC")
        return v


class TaskItemCreate(TaskItemBase):
    """Request schema for creating a task/event."""

    # internal_status is server-set to "confirmed" for MVP


class TaskItemUpdate(BaseModel):
    """Request schema for updating a task/event (partial update).

    Only updatable fields per ScheduleService._UPDATABLE_FIELDS.
    """

    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = None
    due_date: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    all_day: Optional[bool] = None
    tz: Optional[str] = None
    owner: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    internal_status: Optional[str] = None

    @field_validator("tz")
    @classmethod
    def validate_tz(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("Asia/Bangkok", "UTC"):
            raise ValueError("Unsupported timezone. Supported: Asia/Bangkok, UTC")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("pending", "completed", "cancelled"):
            raise ValueError("status must be 'pending', 'completed', or 'cancelled'")
        return v

    @field_validator("internal_status")
    @classmethod
    def validate_internal_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("confirmed", "needs_confirmation"):
            raise ValueError(
                "internal_status must be 'confirmed' or 'needs_confirmation'"
            )
        return v

    # For MVP, internal_status is not updatable by client
    # This validator will reject attempts to set it
    @field_validator("internal_status", mode="after")
    @classmethod
    def reject_internal_status_change(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            raise ValueError(
                "internal_status cannot be modified via API in MVP"
            )
        return v


class TaskItemResponse(TaskItemBase):
    """Response schema for a task/event item."""

    id: str
    status: str
    internal_status: str
    created_at: float
    updated_at: float

    model_config = ConfigDict(from_attributes=True)


class TaskListResponse(BaseModel):
    """Response schema for listing tasks/events."""

    items: List[TaskItemResponse]
    count: int


class CalendarDayResponse(BaseModel):
    """Response schema for calendar day view."""

    date: str
    events: List[TaskItemResponse]
    tasks: List[TaskItemResponse]


class CalendarWeekResponse(BaseModel):
    """Response schema for calendar week view."""

    start_date: str
    end_date: str
    days: List[CalendarDayResponse]


class CalendarMonthResponse(BaseModel):
    """Response schema for calendar month view."""

    year: int
    month: int
    first_weekday: int
    days: List[CalendarDayResponse]


class HistoryEntryResponse(BaseModel):
    """Response schema for a history entry."""

    id: str
    item_id: str
    action: str
    before: Optional[dict] = None
    after: Optional[dict] = None
    changed_fields: List[str] = []
    note: Optional[str] = None
    actor: str = "system"
    created_at: float


class HistoryResponse(BaseModel):
    """Response schema for item history."""

    entries: List[HistoryEntryResponse]
    count: int


class EvidenceCreate(BaseModel):
    """Request schema for attaching evidence."""

    source: str = Field(min_length=1)
    source_ref: str = Field(min_length=1)
    excerpt: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class EvidenceResponse(BaseModel):
    """Response schema for evidence."""

    id: str
    item_id: str
    source: str
    source_ref: str
    excerpt: str
    confidence: float
    created_at: float

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Standardized error response per API Contract v1.1."""

    error: str
    message: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    service: str = "aether-api"
    version: str = "1.0.0"