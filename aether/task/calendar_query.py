"""Calendar queries for Aether Mark 1 — pure functions over TaskItem lists.

Display rules (Phase 2 locked):
- Tasks appear on their due_date only. Tasks without due_date never appear
  in calendar views (they live in lists, not the calendar).
- Events appear on every day their date range covers (interval overlap on
  date granularity):
  - start_date = start_at[:10] — ScheduleService normalizes naive datetimes
    to the item's own tz at the single write boundary, so the date portion
    is already the item's local date. No datetime arithmetic is done here.
  - end_date: end_at empty/None -> same as start_date; all-day -> the date
    string itself; timed with exactly 00:00:00 -> previous day (no midnight
    spill into the next day); other timed -> end_at[:10]. end_date is never
    earlier than start_date.
- Ordering inside a day: events first (by start_at, then title), then tasks
  (by due_date, then title). Empty days are always present in week/month
  views so a UI grid can render them directly.

find_overlapping_events does date-granularity interval overlap — timed
partial overlaps inside one day are a Phase 6 refinement.

Phase 3 requirement (JSON import): every imported item MUST go through
ScheduleService.create() (not repository.save()) so foreign-offset
datetimes are normalized at the same write boundary; items keep their own
offset and display on their own local date.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from aether.task.models import ItemKind, TaskItem, is_date_only, item_to_dict


def event_covers_dates(item: TaskItem) -> Tuple[str, str]:
    """(start_date, end_date) ISO date strings an event occupies on a calendar.

    Returns ("", "") when the event has no start_at (invalid per schema —
    defensive only). See module docstring for the end-date rules.
    """
    start_at = item.start_at or ""
    if not start_at:
        return ("", "")
    start_date = start_at[:10]
    end_at = item.end_at or ""
    if not end_at:
        end_date = start_date
    elif is_date_only(end_at):
        end_date = end_at
    else:
        end_dt = datetime.fromisoformat(end_at)
        midnight = (
            end_dt.hour == 0
            and end_dt.minute == 0
            and end_dt.second == 0
            and end_dt.microsecond == 0
        )
        shift = timedelta(days=1) if midnight else timedelta()
        end_date = (end_dt.date() - shift).isoformat()
    if end_date < start_date:
        end_date = start_date
    return (start_date, end_date)


def items_on_day(items: Iterable[TaskItem], day: str) -> Dict[str, List[TaskItem]]:
    """Items visible on one ISO date ``day`` (YYYY-MM-DD)."""
    events: List[TaskItem] = []
    tasks: List[TaskItem] = []
    for item in items:
        if item.kind == ItemKind.TASK:
            if item.due_date and item.due_date == day:
                tasks.append(item)
        else:
            start_date, end_date = event_covers_dates(item)
            if start_date and start_date <= day <= end_date:
                events.append(item)
    events.sort(key=lambda i: (i.start_at or "", i.title))
    tasks.sort(key=lambda i: (i.due_date or "", i.title))
    return {"events": events, "tasks": tasks}


def day_view(items: Iterable[TaskItem], day: str) -> Dict[str, Any]:
    """One-day view: {"date", "events": [TaskItem], "tasks": [TaskItem]}."""
    bucket = items_on_day(items, day)
    return {"date": day, "events": bucket["events"], "tasks": bucket["tasks"]}


def week_view(items: Iterable[TaskItem], on_date: str) -> Dict[str, Any]:
    """7-day view starting from the Monday of ``on_date``'s ISO week.

    ``on_date`` may be any date in the desired week; it is snapped to
    that week's Monday (ISO weekday, deterministic, no tzdata).
    """
    d = date.fromisoformat(on_date[:10])
    monday = d - timedelta(days=d.weekday())
    days = [day_view(items, (monday + timedelta(days=i)).isoformat()) for i in range(7)]
    return {
        "start_date": monday.isoformat(),
        "end_date": (monday + timedelta(days=6)).isoformat(),
        "days": days,
    }


def month_view(items: Iterable[TaskItem], year: int, month: int) -> Dict[str, Any]:
    """Full-month view: every day of the month, plus grid metadata.

    ``first_weekday`` is the ISO weekday of day 1 (0=Monday) so a UI can
    lay out the grid without extra date math.
    """
    n_days = monthrange(year, month)[1]
    first = date(year, month, 1)
    days = [day_view(items, (first + timedelta(days=i)).isoformat()) for i in range(n_days)]
    return {
        "year": year,
        "month": month,
        "first_weekday": first.weekday(),
        "days": days,
    }


def find_overlapping_events(
    items: Iterable[TaskItem],
    start_at: str,
    end_at: Optional[str] = None,
    *,
    exclude_id: Optional[str] = None,
) -> List[TaskItem]:
    """Events whose covered date range overlaps the window [start_at..end_at].

    Date-granularity interval overlap. ``end_at`` None -> single-day window
    on ``start_at``'s date. ``exclude_id`` skips one item (for update
    conflict checks against the item itself).
    """
    win_start = start_at[:10]
    win_end = end_at[:10] if end_at else win_start
    if win_end < win_start:
        win_end = win_start
    result: List[TaskItem] = []
    for item in items:
        if item.kind != ItemKind.EVENT:
            continue
        if exclude_id and item.id == exclude_id:
            continue
        s, e = event_covers_dates(item)
        if s and s <= win_end and win_start <= e:
            result.append(item)
    result.sort(key=lambda i: (i.start_at or "", i.title))
    return result


def views_to_dicts(view: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a day/week/month view result to JSON-able dicts."""
    if "days" in view:
        days = [day_to_dicts(d) for d in view["days"]]
        out = {k: v for k, v in view.items() if k != "days"}
        out["days"] = days
        return out
    return day_to_dicts(view)


def day_to_dicts(day: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize one day bucket from day_view/items_on_day."""
    return {
        "date": day["date"],
        "events": [item_to_dict(i) for i in day["events"]],
        "tasks": [item_to_dict(i) for i in day["tasks"]],
    }
