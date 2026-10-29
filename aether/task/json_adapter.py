"""JSON import/export for Aether Mark 1 — provider-neutral exchange format.

Format (format_version "1"), independent of any calendar provider:

    {"format_version": "1", "source": "<producer>",
     "exported_at": "<ISO-8601 +07:00>", "items": [<item_to_dict>...]}

Rules (Phase 3 locked):
- Structure/type validation runs FIRST and collects every problem;
  ImportFormatError means zero writes (nothing partially imported).
- Four-digit years only everywhere (due_date, datetimes): a 2-digit year
  is year guessing and is rejected at validation.
- Re-import dedupe at two levels: file content_hash (import_batches,
  canonical JSON so whitespace/key order do not matter) and per-item
  identical content (counted, never rewritten).
- Conflicts (same id, different content) are NEVER silently overwritten:
  default on_conflict="review" parks them in review_queue with the
  {existing, incoming} pair and leaves the stored item untouched;
  "update" writes through ScheduleService.import_item so history gets an
  explicit before/after IMPORTED entry; "skip" only counts.
- All writes of one import run inside one re-entrant repository
  transaction together with the import_batches row — any failure rolls
  back everything, including the batch record.
- Date/tz: naive datetimes normalize to the item tz (single write
  boundary, via _validate inside import_item); offset-aware foreign values
  (+09:00 etc.) are preserved as-is; all-day values stay date-only
  (no midnight invented — date-only strings are never passed through
  datetime normalization).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from aether.task.models import (
    DEFAULT_TZ,
    ImportBatch,
    InternalStatus,
    ItemKind,
    ItemStatus,
    ReviewEntry,
    ReviewState,
    TaskItem,
    is_date_only,
    item_to_dict,
    normalize_datetime,
    tzinfo_for,
)
from aether.task.repository import SqliteScheduleRepository
from aether.task.service import ScheduleService

FORMAT_VERSION = "1"

_ON_CONFLICTS = ("review", "update", "skip")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ImportFormatError(ValueError):
    """Structure/type validation failed. Carries every problem found."""

    def __init__(self, errors: List[str]) -> None:
        self.errors: List[str] = list(errors)
        head = "; ".join(self.errors[:5])
        if len(self.errors) > 5:
            head += f" (+{len(self.errors) - 5} more)"
        super().__init__(head)


@dataclass
class ImportResult:
    """Outcome of one import_data() run (also the command response)."""

    ok: bool = True
    already_imported: bool = False
    batch_id: Optional[str] = None
    imported: int = 0
    duplicates: int = 0
    conflicts: int = 0
    updated: int = 0
    parked: int = 0
    skipped: int = 0
    conflict_ids: List[str] = field(default_factory=list)
    message: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "already_imported": self.already_imported,
            "batch_id": self.batch_id,
            "imported": self.imported,
            "duplicates": self.duplicates,
            "conflicts": self.conflicts,
            "updated": self.updated,
            "parked": self.parked,
            "skipped": self.skipped,
            "conflict_ids": list(self.conflict_ids),
            "message": self.message,
        }


# ── Export ─────────────────────────────────────────────────────────


def export_items(items: Iterable[TaskItem], *, source: str = "aether-mark1") -> Dict[str, Any]:
    """Build the export payload (plain dict, stable under dumps())."""
    now = datetime.now(timezone.utc).astimezone(tzinfo_for(DEFAULT_TZ))
    return {
        "format_version": FORMAT_VERSION,
        "source": source,
        "exported_at": now.isoformat(timespec="seconds"),
        "items": [item_to_dict(i) for i in items],
    }


def dumps(payload: Dict[str, Any]) -> str:
    """Canonical JSON: stable key order, Thai not escaped, compact."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def export_to_file(items: Iterable[TaskItem], path: str, *, source: str = "aether-mark1") -> str:
    """Write the export to ``path`` (UTF-8, parents created). Returns the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps(export_items(items, source=source)) + "\n", encoding="utf-8")
    return str(target)


def loads(text: str) -> Dict[str, Any]:
    """Parse JSON text into a payload dict (json.JSONDecodeError on bad syntax)."""
    data = json.loads(text)
    return data


def content_hash(payload: Dict[str, Any]) -> str:
    """sha256 of the canonical serialization (whitespace/order insensitive)."""
    return hashlib.sha256(dumps(payload).encode("utf-8")).hexdigest()


# ── Validation (structure + types, nothing else) ───────────────────


def load_and_validate(data: Any) -> List[Dict[str, Any]]:
    """Validate payload structure/types; return the raw item dicts.

    Raises ImportFormatError listing every problem — callers must treat
    that as zero writes.
    """
    if not isinstance(data, dict):
        raise ImportFormatError([f"root: expected a JSON object, got {type(data).__name__}"])

    errors: List[str] = []

    version = data.get("format_version")
    if version != FORMAT_VERSION:
        errors.append(f"format_version: expected {FORMAT_VERSION!r}, got {version!r}")

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        errors.append(f"items: expected a list, got {type(raw_items).__name__}")
        raw_items = []
    for i, raw in enumerate(raw_items):
        errors.extend(_validate_item_raw(i, raw))

    if errors:
        raise ImportFormatError(errors)
    return raw_items


def _as_aware_datetime(value: str, tz_name: Any) -> Optional[datetime]:
    """ISO-8601 string -> offset-aware datetime (naive gets ``tz_name``).

    Returns None when the value is unparsable or the tz is unsupported —
    both cases are already reported by the structural checks above, so the
    chronology check simply skips them. Mirrors ScheduleService._validate
    (same normalize-then-compare semantics) so adapter and service agree.
    """
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        try:
            dt = dt.replace(tzinfo=tzinfo_for(tz_name))
        except (KeyError, TypeError, ValueError):
            return None
    return dt


def _validate_item_raw(index: int, raw: Any) -> List[str]:
    prefix = f"items[{index}]"
    if not isinstance(raw, dict):
        return [f"{prefix}: expected an object, got {type(raw).__name__}"]
    errors: List[str] = []

    item_id = raw.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        errors.append(f"{prefix}.id: expected a non-empty string")

    kind = raw.get("kind")
    if kind not in ("task", "event"):
        errors.append(f"{prefix}.kind: expected 'task' or 'event', got {kind!r}")

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"{prefix}.title: expected a non-empty string")

    for name in ("description", "owner", "source"):
        value = raw.get(name)
        if value is not None and not isinstance(value, str):
            errors.append(f"{prefix}.{name}: expected string or null, got {type(value).__name__}")

    status = raw.get("status", "pending")
    if status not in tuple(s.value for s in ItemStatus):
        errors.append(f"{prefix}.status: unknown value {status!r}")
    internal = raw.get("internal_status", "confirmed")
    if internal not in tuple(s.value for s in InternalStatus):
        errors.append(f"{prefix}.internal_status: unknown value {internal!r}")

    all_day = raw.get("all_day", False)
    if not isinstance(all_day, bool):
        errors.append(f"{prefix}.all_day: expected boolean, got {type(all_day).__name__}")

    tz = raw.get("tz", DEFAULT_TZ)
    if not isinstance(tz, str):
        errors.append(f"{prefix}.tz: expected string, got {type(tz).__name__}")
    else:
        try:
            tzinfo_for(tz)
        except ValueError as exc:
            errors.append(f"{prefix}.tz: {exc}")

    # Dates: four-digit years only; date-only vs timed enforced per kind.
    due_date = raw.get("due_date")
    if due_date is not None:
        if not isinstance(due_date, str) or not _DATE_RE.match(due_date) or not is_date_only(due_date):
            errors.append(
                f"{prefix}.due_date: expected YYYY-MM-DD with a 4-digit year, got {due_date!r}"
            )

    for name in ("start_at", "end_at"):
        value = raw.get(name)
        if value is None:
            continue
        if not isinstance(value, str):
            errors.append(f"{prefix}.{name}: expected string or null, got {type(value).__name__}")
            continue
        date_part = value[:10]
        if not _DATE_RE.match(date_part):
            errors.append(
                f"{prefix}.{name}: date part must be YYYY-MM-DD with a 4-digit year, got {value!r}"
            )
            continue
        if is_date_only(value):
            if not all_day:
                errors.append(
                    f"{prefix}.{name}: date-only {value!r} requires all_day=true "
                    "(a bare date is never turned into midnight)"
                )
            continue
        if all_day:
            errors.append(
                f"{prefix}.{name}: all_day=true requires YYYY-MM-DD, got {value!r}"
            )
            continue
        if "T" not in value:
            errors.append(f"{prefix}.{name}: timed value must be ISO-8601 with 'T', got {value!r}")
            continue
        try:
            datetime.fromisoformat(value)
        except ValueError:
            errors.append(f"{prefix}.{name}: not a valid ISO-8601 datetime: {value!r}")

    if kind == "event":
        if due_date is not None:
            errors.append(f"{prefix}: events use start_at, not due_date")
        if raw.get("start_at") is None:
            errors.append(f"{prefix}: events require start_at")
    if kind == "task" and all_day:
        errors.append(f"{prefix}: all_day is only valid for events")

    for name in ("created_at", "updated_at"):
        value = raw.get(name)
        if value is not None and not isinstance(value, (int, float)):
            errors.append(f"{prefix}.{name}: expected number or null, got {type(value).__name__}")

    # Chronology: compare instants, never raw strings (mixed offsets make
    # lexicographic order meaningless). Date-only stays string-compared.
    start_at, end_at = raw.get("start_at"), raw.get("end_at")
    if isinstance(start_at, str) and isinstance(end_at, str):
        if is_date_only(start_at) and is_date_only(end_at):
            if end_at < start_at:
                errors.append(f"{prefix}: end {end_at!r} is before start {start_at!r}")
        elif "T" in start_at and "T" in end_at:
            start_dt = _as_aware_datetime(start_at, tz)
            end_dt = _as_aware_datetime(end_at, tz)
            if start_dt is not None and end_dt is not None and end_dt < start_dt:
                errors.append(f"{prefix}: end {end_at!r} is before start {start_at!r}")

    return errors


# ── Item reconstruction ────────────────────────────────────────────


def _normalize_dt(value: Optional[str], tz: str) -> Optional[str]:
    """Attach the item tz to naive datetimes; date-only stays date-only."""
    if value is None or is_date_only(value):
        return value
    return normalize_datetime(value, tz)


def item_from_dict(data: Dict[str, Any]) -> TaskItem:
    """Build a TaskItem from a validated raw dict (id/status/timestamps kept).

    Naive datetimes gain the item tz here so conflict comparison against
    stored (already normalized) items is exact.
    """
    tz = data.get("tz") or DEFAULT_TZ
    return TaskItem(
        id=data["id"],
        kind=ItemKind(data["kind"]),
        title=data["title"],
        description=data.get("description") or "",
        status=ItemStatus(data.get("status") or ItemStatus.PENDING.value),
        internal_status=InternalStatus(data.get("internal_status") or InternalStatus.CONFIRMED.value),
        due_date=data.get("due_date"),
        start_at=_normalize_dt(data.get("start_at"), tz),
        end_at=_normalize_dt(data.get("end_at"), tz),
        all_day=bool(data.get("all_day", False)),
        tz=tz,
        owner=data.get("owner"),
        source=data.get("source") or "manual",
        created_at=float(data.get("created_at") or time.time()),
        updated_at=float(data.get("updated_at") or time.time()),
    )


# ── Import ─────────────────────────────────────────────────────────


def import_data(
    service: ScheduleService,
    repo: SqliteScheduleRepository,
    data: Any,
    *,
    on_conflict: str = "review",
    actor: str = "import",
) -> ImportResult:
    """Validate + apply one payload. Atomic: all writes share one transaction.

    Order: validate (raises ImportFormatError -> zero writes) -> file-level
    content_hash dedupe -> per-item classification -> single transaction
    (items + review rows + import_batches row) -> commit.
    """
    if on_conflict not in _ON_CONFLICTS:
        raise ImportFormatError(
            [f"on_conflict: expected one of {', '.join(_ON_CONFLICTS)}, got {on_conflict!r}"]
        )

    raw_items = load_and_validate(data)  # raises -> zero writes

    digest = content_hash(data)
    prior = repo.find_batch_by_hash(digest)
    if prior is not None:
        return ImportResult(
            already_imported=True,
            batch_id=prior.id,
            duplicates=len(raw_items),
            message=f"already imported as batch {prior.id} (content unchanged, nothing written)",
        )

    new_items: List[TaskItem] = []
    identical: List[str] = []
    conflicts: List[Tuple[TaskItem, TaskItem]] = []
    for raw in raw_items:
        incoming = item_from_dict(raw)
        existing = repo.find_by_id(incoming.id)
        if existing is None:
            new_items.append(incoming)
        elif item_to_dict(existing) == item_to_dict(incoming):
            identical.append(incoming.id)
        else:
            conflicts.append((existing, incoming))

    result = ImportResult(
        imported=len(new_items),
        duplicates=len(identical),
        conflicts=len(conflicts),
        conflict_ids=[incoming.id for _, incoming in conflicts],
    )

    with repo.transaction():
        for item in new_items:
            service.import_item(item, actor=actor)

        if on_conflict == "update":
            for existing, incoming in conflicts:
                service.import_item(incoming, existing=existing, actor=actor)
            result.updated = len(conflicts)
            conflict_action = "updated"
        elif on_conflict == "review":
            for existing, incoming in conflicts:
                repo.enqueue_review(ReviewEntry(
                    item_id=incoming.id,
                    reason="import conflict",
                    payload={
                        "existing": item_to_dict(existing),
                        "incoming": item_to_dict(incoming),
                        "on_conflict": "review",
                        "kind": "import_conflict",
                    },
                    confidence=0.5,
                    state=ReviewState.PENDING,
                ))
            result.parked = len(conflicts)
            conflict_action = "parked for review"
        else:  # skip
            result.skipped = len(conflicts)
            conflict_action = "skipped"

        batch = ImportBatch(
            source="json",
            format_version=FORMAT_VERSION,
            content_hash=digest,
            item_count=len(raw_items),
            stats={
                "imported": result.imported,
                "duplicates": result.duplicates,
                "conflicts": result.conflicts,
                "updated": result.updated,
                "parked": result.parked,
                "skipped": result.skipped,
                "on_conflict": on_conflict,
                "actor": actor,
            },
            imported_at=time.time(),
        )
        repo.record_batch(batch)
        result.batch_id = batch.id

    result.message = (
        f"imported {result.imported}, duplicates {result.duplicates}, "
        f"conflicts {result.conflicts} ({conflict_action})"
    )
    return result
