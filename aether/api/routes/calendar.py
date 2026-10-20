"""Calendar query endpoints for Aether API.

Implements Day/Week/Month calendar views per API Contract v1.1.
All views use calendar_query pure functions over TaskItem lists.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from aether.api.dependencies import get_schedule_service
from aether.api.schemas import (
    CalendarDayResponse,
    CalendarMonthResponse,
    CalendarWeekResponse,
)
from aether.task import calendar_query
from aether.task.service import ScheduleService


router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/day", response_model=CalendarDayResponse)
async def calendar_day(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    service: "ScheduleService" = Depends(get_schedule_service),
) -> CalendarDayResponse:
    """Get calendar view for a single day.

    Returns events and tasks visible on the given date.
    Follows calendar_query.day_view semantics:
    - Tasks appear only on their due_date
    - Events appear on every day their date range covers
    - Shows pending, completed, and cancelled items (no status filtering)
    """
    items = service.list()
    view = calendar_query.day_view(items, date)
    return CalendarDayResponse(
        date=view["date"],
        events=[{"id": i.id, "kind": i.kind.value, "title": i.title, "start_at": i.start_at, "end_at": i.end_at, "all_day": i.all_day} for i in view["events"]],
        tasks=[{"id": i.id, "kind": i.kind.value, "title": i.title, "due_date": i.due_date} for i in view["tasks"]],
    )


@router.get("/week", response_model=CalendarWeekResponse)
async def calendar_week(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    service: "ScheduleService" = Depends(get_schedule_service),
) -> CalendarWeekResponse:
    """Get calendar view for a 7-day week starting from Monday.

    The given date is snapped to its ISO week's Monday.
    Returns 7 days of calendar views.
    """
    items = service.list()
    view = calendar_query.week_view(service.list(), date)
    return CalendarWeekResponse(
        start_date=view["start_date"],
        end_date=view["end_date"],
        days=[
            CalendarDayResponse(
                date=d["date"],
                events=[{"id": i.id, "kind": i.kind.value, "title": i.title, "start_at": i.start_at, "end_at": i.end_at, "all_day": i.all_day} for i in d["events"]],
                tasks=[{"id": i.id, "kind": i.kind.value, "title": i.title, "due_date": i.due_date} for i in d["tasks"]],
            )
            for d in view["days"]
        ],
    )


@router.get("/month", response_model=CalendarMonthResponse)
async def calendar_month(
    year: int = Query(..., ge=1900, le=2100),
    month: int = Query(..., ge=1, le=12),
    service: "ScheduleService" = Depends(get_schedule_service),
) -> CalendarMonthResponse:
    """Get calendar view for a full month.

    Returns all days of the month with first_weekday (0=Monday).
    """
    items = service.list()
    view = calendar_query.month_view(items, year, month)
    return CalendarMonthResponse(
        year=view["year"],
        month=view["month"],
        first_weekday=view["first_weekday"],
        days=[
            CalendarDayResponse(
                date=d["date"],
                events=[{"id": i.id, "kind": i.kind.value, "title": i.title, "start_at": i.start_at, "end_at": i.end_at, "all_day": i.all_day} for i in d["events"]],
                tasks=[{"id": i.id, "kind": i.kind.value, "title": i.title, "due_date": i.due_date} for i in d["tasks"]],
            )
            for d in view["days"]
        ],
    )