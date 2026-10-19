"""Aether Mark 1 — schedule domain (tasks + calendar events).

Single-table design behind `data/tasks.db` (see aether.task.schema):
    items        — one row per task or calendar event (kind column)
    evidence     — source references attached to items
    item_history — append-only audit trail (survives item deletion)
    review_queue — uncertain extractions awaiting human confirmation
    import_batches — JSON import bookkeeping (dedupe via content hash)

Frozen dataclasses mirror the Memory Core domain style. All timestamps are
epoch seconds (REAL) unless noted; `due_date` and all-day values are
"YYYY-MM-DD" strings; timed values are ISO-8601 strings with offset.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

DEFAULT_TZ = "Asia/Bangkok"

# Fixed-offset registry: Windows has no system IANA tz database and the
# `tzdata` package is not a declared dependency. Asia/Bangkok is fixed
# UTC+7 year-round (no DST), so a fixed offset is exact. Add entries here
# only with the same no-DST guarantee.
TZ_OFFSETS: Dict[str, timezone] = {
    "Asia/Bangkok": timezone(timedelta(hours=7)),
    "UTC": timezone.utc,
}


def tzinfo_for(name: str) -> timezone:
    """Return the fixed-offset tzinfo for a supported timezone name."""
    try:
        return TZ_OFFSETS[name]
    except KeyError:
        supported = ", ".join(sorted(TZ_OFFSETS))
        raise ValueError(f"unsupported timezone {name!r} (supported: {supported})")


def normalize_datetime(value: str, tz_name: str) -> str:
    """Parse an ISO-8601 datetime and return canonical offset-aware ISO string.

    Naive input is interpreted in `tz_name`. Offset-aware input is preserved
    as given (canonicalized by fromisoformat/isoformat).
    Raises ValueError on unparsable input or unsupported timezone.
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tzinfo_for(tz_name))
    return dt.isoformat()


def is_date_only(value: str) -> bool:
    """True when value is a bare YYYY-MM-DD date string."""
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


class ItemKind(str, Enum):
    TASK = "task"
    EVENT = "event"


class ItemStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InternalStatus(str, Enum):
    CONFIRMED = "confirmed"
    NEEDS_CONFIRMATION = "needs_confirmation"


class HistoryAction(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DELETED = "deleted"
    IMPORTED = "imported"
    REVIEWED = "reviewed"


class ReviewState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EDITED = "edited"


def _hex_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class TaskItem:
    """One scheduled item — a task (has deadline) or an event (has start).

    Field rules per kind (enforced by ScheduleService + SQL CHECKs):
        task:  due_date optional date-only; all_day forbidden; timed
               start_at/end_at optional
        event: start_at required; all_day=1 keeps date-only strings (no
               midnight invented); due_date forbidden
    """

    id: str = field(default_factory=lambda: _hex_id("item"))
    kind: ItemKind = ItemKind.TASK
    title: str = ""
    description: str = ""
    status: ItemStatus = ItemStatus.PENDING
    internal_status: InternalStatus = InternalStatus.CONFIRMED
    due_date: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    all_day: bool = False
    tz: str = DEFAULT_TZ
    owner: Optional[str] = None
    source: str = "manual"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class Evidence:
    """A source reference proving where an item came from."""

    id: str = field(default_factory=lambda: _hex_id("evid"))
    item_id: str = ""
    source: str = "manual"
    source_ref: str = ""
    excerpt: str = ""
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class HistoryEntry:
    """One append-only audit record. Survives item deletion (no FK)."""

    id: str = field(default_factory=lambda: _hex_id("hist"))
    item_id: str = ""
    action: HistoryAction = HistoryAction.CREATED
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    changed_fields: List[str] = field(default_factory=list)
    note: Optional[str] = None
    actor: str = "system"
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ReviewEntry:
    """One review-queue row for an uncertain item."""

    id: str = field(default_factory=lambda: _hex_id("rev"))
    item_id: str = ""
    reason: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    state: ReviewState = ReviewState.PENDING
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None


@dataclass(frozen=True)
class ImportBatch:
    """One JSON import run; content_hash dedupes re-imports."""

    id: str = field(default_factory=lambda: _hex_id("imp"))
    source: str = "json"
    format_version: str = "1"
    content_hash: str = ""
    item_count: int = 0
    stats: Dict[str, Any] = field(default_factory=dict)
    imported_at: float = field(default_factory=time.time)


def item_to_dict(item: TaskItem) -> Dict[str, Any]:
    """Serialize a TaskItem to a plain dict (enum values as strings)."""
    return {
        "id": item.id,
        "kind": item.kind.value,
        "title": item.title,
        "description": item.description,
        "status": item.status.value,
        "internal_status": item.internal_status.value,
        "due_date": item.due_date,
        "start_at": item.start_at,
        "end_at": item.end_at,
        "all_day": item.all_day,
        "tz": item.tz,
        "owner": item.owner,
        "source": item.source,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }
