"""Calendar query endpoints for Aether API.

Implements Day/Week/Month calendar views per API Contract v1.1.
Thin adapter: the ScheduleEngine's calendar_query pure functions do the
date/status work and its own ``views_to_dicts`` serializer produces the
payload — the API layer only wires HTTP to them. Calendar views show ALL
statuses (pending, completed, cancelled) — no status filtering here.
"""

from __future__ import annotations

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
    """Items visible on one date.

    Follows calendar_query.day_view semantics:
    - Tasks appear only on their due_date
    - Events appear on every day their date range covers
    - Shows pending, completed, and cancelled items (no status filtering)
    """
    view = calendar_query.day_view(service.list(), date)
    return CalendarDayResponse(**calendar_query.views_to_dicts(view))


@router.get("/week", response_model=CalendarWeekResponse)
async def calendar_week(
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    service: "ScheduleService" = Depends(get_schedule_service),
) -> CalendarWeekResponse:
    """7 days starting from the Monday of ``date``'s ISO week."""
    view = calendar_query.week_view(service.list(), date)
    return CalendarWeekResponse(**calendar_query.views_to_dicts(view))


@router.get("/month", response_model=CalendarMonthResponse)
async def calendar_month(
    year: int = Query(..., ge=1900, le=2100),
    month: int = Query(..., ge=1, le=12),
    service: "ScheduleService" = Depends(get_schedule_service),
) -> CalendarMonthResponse:
    """Every day of the month plus grid metadata (first_weekday, 0=Monday)."""
    view = calendar_query.month_view(service.list(), year, month)
    return CalendarMonthResponse(**calendar_query.views_to_dicts(view))
