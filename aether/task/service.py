"""ScheduleService — business rules for Mark 1 tasks and calendar events.

All writes go through this service (never the repository directly), so
every mutation is validated, conflict-checked, and audited atomically:
item write + history append share one transaction.

Rules enforced here (SQL CHECKs are the backstop):
    - title non-empty; timezone supported
    - task:  due_date optional date-only; all_day forbidden
    - event: start_at required; all_day keeps date-only strings (no
             midnight invented); due_date forbidden
    - end_at >= start_at when both present
    - status transitions: pending → completed (task only) | cancelled;
      terminal states never revert silently
    - update never touches id/created_at; kind is immutable
    - optimistic concurrency: optional expected_updated_at guard
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace
from datetime import datetime
from typing import Any, Dict, List, Optional

from aether.core.interfaces.i_schedule_repository import IScheduleRepository
from aether.task.models import (
    DEFAULT_TZ,
    Evidence,
    HistoryAction,
    HistoryEntry,
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

logger = logging.getLogger("Aether.task.service")


class ScheduleError(RuntimeError):
    """Base error for schedule operations."""


class ScheduleValidationError(ScheduleError):
    """Input failed a business rule."""


class ScheduleNotFoundError(ScheduleError):
    """Referenced item does not exist."""


class ScheduleConflictError(ScheduleError):
    """Optimistic-concurrency guard failed (item changed underneath)."""


# Fields an update may change. id/created_at/kind are immutable.
_UPDATABLE_FIELDS = frozenset(
    {
        "title",
        "description",
        "due_date",
        "start_at",
        "end_at",
        "all_day",
        "tz",
        "owner",
        "source",
        "status",
        "internal_status",
    }
)


class ScheduleService:
    """Validated, audited CRUD for schedule items."""

    def __init__(self, repository: IScheduleRepository) -> None:
        self._repo = repository

    # ── Create ─────────────────────────────────────────────────────

    def create(
        self,
        kind: ItemKind,
        title: str,
        *,
        description: str = "",
        due_date: Optional[str] = None,
        start_at: Optional[str] = None,
        end_at: Optional[str] = None,
        all_day: bool = False,
        tz: str = DEFAULT_TZ,
        owner: Optional[str] = None,
        source: str = "manual",
        internal_status: InternalStatus = InternalStatus.CONFIRMED,
        actor: str = "user",
    ) -> TaskItem:
        """Create one item + its 'created' history entry, atomically."""
        now = time.time()
        item = TaskItem(
            kind=kind,
            title=title,
            description=description,
            status=ItemStatus.PENDING,
            internal_status=internal_status,
            due_date=due_date,
            start_at=start_at,
            end_at=end_at,
            all_day=all_day,
            tz=tz,
            owner=owner,
            source=source,
            created_at=now,
            updated_at=now,
        )
        item = self._validate(item)
        entry = HistoryEntry(
            item_id=item.id,
            action=HistoryAction.CREATED,
            before=None,
            after=item_to_dict(item),
            actor=actor,
            created_at=now,
        )
        with self._repo.transaction():
            self._repo.save(item)
            self._repo.append_history(entry)
        logger.info("item created: %s (%s) %r", item.id, item.kind.value, item.title)
        return item

    # ── Read ───────────────────────────────────────────────────────

    def get(self, item_id: str) -> TaskItem:
        """Fetch one item by id (raises if missing)."""
        item = self._repo.find_by_id(item_id)
        if item is None:
            raise ScheduleNotFoundError(f"item not found: {item_id}")
        return item

    def list(
        self,
        kind: Optional[ItemKind] = None,
        status: Optional[ItemStatus] = None,
    ) -> List[TaskItem]:
        """List items, optionally filtered by kind and/or status."""
        return self._repo.find_all(kind=kind, status=status)

    def history(self, item_id: str, limit: int = 100) -> List[HistoryEntry]:
        """Audit trail for one item, newest first."""
        return self._repo.get_history(item_id, limit=limit)

    # ── Update ─────────────────────────────────────────────────────

    def update(
        self,
        item_id: str,
        *,
        expected_updated_at: Optional[float] = None,
        actor: str = "user",
        **changes: Any,
    ) -> TaskItem:
        """Update allowed fields; writes 'updated' history atomically.

        Pass expected_updated_at (the updated_at you last read) for
        optimistic concurrency — a mismatch raises ScheduleConflictError
        and nothing is written. kind/id/created_at are immutable.
        """
        unknown = set(changes) - _UPDATABLE_FIELDS
        if unknown:
            raise ScheduleValidationError(
                f"immutable or unknown fields: {sorted(unknown)}"
            )
        if not changes:
            raise ScheduleValidationError("no changes given")
        # Coerce enum fields so string inputs stay type-correct.
        if "status" in changes:
            changes["status"] = ItemStatus(changes["status"])
        if "internal_status" in changes:
            changes["internal_status"] = InternalStatus(changes["internal_status"])
        now = time.time()
        with self._repo.transaction():
            current = self._get_locked(item_id)
            if (
                "status" in changes
                and current.status is not ItemStatus.PENDING
                and changes["status"] is not current.status
            ):
                raise ScheduleValidationError(
                    f"status is terminal ({current.status.value}); "
                    "use complete()/cancel() and never revert silently"
                )
            if (
                expected_updated_at is not None
                and current.updated_at != expected_updated_at
            ):
                raise ScheduleConflictError(
                    f"item {item_id} changed since "
                    f"updated_at={expected_updated_at} "
                    f"(current={current.updated_at})"
                )
            merged = replace(current, **changes, updated_at=now)
            merged = self._validate(merged)
            changed = self._changed_fields(current, merged, changes.keys())
            entry = HistoryEntry(
                item_id=item_id,
                action=HistoryAction.UPDATED,
                before=item_to_dict(current),
                after=item_to_dict(merged),
                changed_fields=changed,
                actor=actor,
                created_at=now,
            )
            self._repo.save(merged)
            self._repo.append_history(entry)
        logger.info("item updated: %s fields=%s", item_id, changed)
        return merged

    # ── Reviews (Phase 4) ───────────────────────────────────────────

    def list_pending_reviews(self) -> List[ReviewEntry]:
        """List pending reviews."""
        return self._repo.list_reviews(ReviewState.PENDING)

    def list_reviews(self, state: Optional[ReviewState] = None) -> List[ReviewEntry]:
        """List reviews optionally filtered by state."""
        return self._repo.list_reviews(state)

    def resolve_review(
        self,
        review_id: str,
        decision: str,
        *,
        corrected_fields: Optional[Dict[str, Any]] = None,
        actor: str = "user",
    ) -> Dict[str, Any]:
        """Resolve a pending review according to Phase 4 matrix.

        decision: confirm|edit|reject
        """
        decision_l = decision.lower()
        if decision_l not in ("confirm", "edit", "reject"):
            raise ScheduleValidationError(f"invalid decision: {decision!r}")

        reviews = self._repo.list_reviews()
        review = None
        for r in reviews:
            if r.id == review_id:
                review = r
                break
        if review is None:
            raise ScheduleNotFoundError(f"review not found: {review_id}")
        if review.state != ReviewState.PENDING:
            raise ScheduleConflictError(f"review {review_id} not pending")

        now = time.time()
        corrected_fields = corrected_fields or {}

        if decision_l == "reject":
            with self._repo.transaction():
                ok = self._repo.resolve_review(review_id, ReviewState.REJECTED, now)
                if not ok:
                    raise ScheduleConflictError(f"review {review_id} could not be resolved")
                self.delete(review.item_id, actor=actor)
            return {"ok": True, "decision": "reject", "review_id": review_id, "item_id": review.item_id}

        if decision_l == "confirm":
            with self._repo.transaction():
                ok = self._repo.resolve_review(review_id, ReviewState.CONFIRMED, now)
                if not ok:
                    raise ScheduleConflictError(f"review {review_id} could not be resolved")
                item = self.update(review.item_id, internal_status=InternalStatus.CONFIRMED, actor=actor)
                entry = HistoryEntry(
                    item_id=item.id,
                    action=HistoryAction.REVIEWED,
                    before=None,
                    after=item_to_dict(item),
                    changed_fields=[],
                    note="confirmed",
                    actor=actor,
                    created_at=now,
                )
                self._repo.append_history(entry)
            return {"ok": True, "decision": "confirm", "review_id": review_id, "item_id": item.id, "item": item_to_dict(item)}

        # edit
        with self._repo.transaction():
            ok = self._repo.resolve_review(review_id, ReviewState.EDITED, now)
            if not ok:
                raise ScheduleConflictError(f"review {review_id} could not be resolved")
            changes = dict(corrected_fields)
            changes["internal_status"] = InternalStatus.CONFIRMED
            item = self.update(review.item_id, actor=actor, **changes)
            entry = HistoryEntry(
                item_id=item.id,
                action=HistoryAction.REVIEWED,
                before=None,
                after=item_to_dict(item),
                changed_fields=[],
                note="edited",
                actor=actor,
                created_at=now,
            )
            self._repo.append_history(entry)
        return {"ok": True, "decision": "edit", "review_id": review_id, "item_id": item.id, "item": item_to_dict(item)}

    def complete(self, item_id: str, *, actor: str = "user") -> TaskItem:
        """Mark a pending task completed (events cannot be completed)."""
        now = time.time()
        with self._repo.transaction():
            current = self._get_locked(item_id)
            if current.kind is not ItemKind.TASK:
                raise ScheduleValidationError(
                    f"only tasks can be completed, {item_id} is {current.kind.value}"
                )
            if current.status is not ItemStatus.PENDING:
                raise ScheduleValidationError(
                    f"cannot complete item in status {current.status.value}"
                )
            merged = replace(
                current, status=ItemStatus.COMPLETED, updated_at=now
            )
            entry = HistoryEntry(
                item_id=item_id,
                action=HistoryAction.COMPLETED,
                before=item_to_dict(current),
                after=item_to_dict(merged),
                changed_fields=["status"],
                actor=actor,
                created_at=now,
            )
            self._repo.save(merged)
            self._repo.append_history(entry)
        logger.info("item completed: %s", item_id)
        return merged

    def cancel(self, item_id: str, *, actor: str = "user", reason: str = "") -> TaskItem:
        """Cancel a pending item (task or event)."""
        now = time.time()
        with self._repo.transaction():
            current = self._get_locked(item_id)
            if current.status is not ItemStatus.PENDING:
                raise ScheduleValidationError(
                    f"cannot cancel item in status {current.status.value}"
                )
            merged = replace(current, status=ItemStatus.CANCELLED, updated_at=now)
            entry = HistoryEntry(
                item_id=item_id,
                action=HistoryAction.CANCELLED,
                before=item_to_dict(current),
                after=item_to_dict(merged),
                changed_fields=["status"],
                note=reason or None,
                actor=actor,
                created_at=now,
            )
            self._repo.save(merged)
            self._repo.append_history(entry)
        logger.info("item cancelled: %s reason=%r", item_id, reason)
        return merged

    def delete(self, item_id: str, *, actor: str = "user") -> None:
        """Delete one item; writes a 'deleted' history entry first.

        Evidence + review rows cascade away; the history entry survives
        (item_history has no foreign key by design).
        """
        now = time.time()
        with self._repo.transaction():
            current = self._get_locked(item_id)
            entry = HistoryEntry(
                item_id=item_id,
                action=HistoryAction.DELETED,
                before=item_to_dict(current),
                after=None,
                actor=actor,
                created_at=now,
            )
            self._repo.append_history(entry)
            self._repo.delete(item_id)
        logger.info("item deleted: %s", item_id)

    def import_item(
        self,
        item: TaskItem,
        *,
        existing: Optional[TaskItem] = None,
        actor: str = "import",
    ) -> TaskItem:
        """Validate + persist one imported item (id preserved), history IMPORTED.

        Used by the JSON adapter: domain rules and tz normalization are
        identical to create() (single _validate path). `existing` (same id,
        different content) supplies the history before-image for an explicit
        on_conflict="update" overwrite — never a silent one.
        """
        now = time.time()
        item = self._validate(item)
        entry = HistoryEntry(
            item_id=item.id,
            action=HistoryAction.IMPORTED,
            before=item_to_dict(existing) if existing is not None else None,
            after=item_to_dict(item),
            actor=actor,
            created_at=now,
        )
        with self._repo.transaction():
            self._repo.save(item)
            self._repo.append_history(entry)
        logger.info("item imported: %s (%s) %r", item.id, item.kind.value, item.title)
        return item

    def attach_evidence(
        self,
        item_id: str,
        source: str,
        source_ref: str,
        excerpt: str = "",
        confidence: float = 1.0,
    ) -> Evidence:
        """Attach one evidence row to an existing item."""
        self._get_locked(item_id)
        evidence = Evidence(
            item_id=item_id,
            source=source,
            source_ref=source_ref,
            excerpt=excerpt,
            confidence=confidence,
        )
        with self._repo.transaction():
            self._repo.add_evidence([evidence])
        return evidence

    # ── Validation ─────────────────────────────────────────────────

    def _validate(self, item: TaskItem) -> TaskItem:
        """Full kind-aware rule matrix; returns the normalized item."""
        if not item.title or not item.title.strip():
            raise ScheduleValidationError("title must be non-empty")
        # Confirmed items must use a supported timezone. Uncertain (needs
        # confirmation) items may carry an unsupported tz name verbatim so
        # the original identity is preserved for review (R4) instead of
        # being guessed or rejected outright.
        if item.internal_status is InternalStatus.CONFIRMED:
            try:
                tzinfo_for(item.tz)
            except ValueError as exc:
                raise ScheduleValidationError(str(exc)) from exc

        # Kind rules.
        if item.kind is ItemKind.TASK:
            if item.all_day:
                raise ScheduleValidationError("all_day is only valid for events")
            if item.due_date is not None and not is_date_only(item.due_date):
                raise ScheduleValidationError(
                    f"due_date must be YYYY-MM-DD, got {item.due_date!r}"
                )
        else:  # EVENT
            if item.due_date is not None:
                raise ScheduleValidationError(
                    "events use start_at, not due_date"
                )
            # Uncertain extractions may not yet have a start_at; only confirmed
            # items must satisfy the full event shape.
            if item.start_at is None and item.internal_status is InternalStatus.CONFIRMED:
                raise ScheduleValidationError("events require start_at")

        # all_day handling: keep date-only values date-only (no midnight).
        if item.all_day:
            if item.kind is not ItemKind.EVENT:
                raise ScheduleValidationError("all_day is only valid for events")
            for name, value in (("start_at", item.start_at), ("end_at", item.end_at)):
                if value is not None and not is_date_only(value):
                    raise ScheduleValidationError(
                        f"{name} must be YYYY-MM-DD when all_day=True, got {value!r}"
                    )
            if item.end_at is not None and item.start_at is not None:
                # ISO date strings compare chronologically lexicographically.
                if item.end_at < item.start_at:
                    raise ScheduleValidationError(
                        f"end_at {item.end_at} is before start_at {item.start_at}"
                    )
        else:
            # Timed values must be ISO-8601; naive times get the item tz offset.
            # A bare date is never turned into midnight (locked rule): date-only
            # start_at/end_at require all_day=True (json_adapter enforces the
            # same at validation).
            for name, value in (("start_at", item.start_at), ("end_at", item.end_at)):
                if value is not None and is_date_only(value):
                    raise ScheduleValidationError(
                        f"{name} must include a time when all_day=False "
                        f"(a bare date is never turned into midnight), got {value!r}"
                    )
            if item.start_at is not None:
                try:
                    start = normalize_datetime(item.start_at, item.tz)
                except ValueError:
                    # Preserve original (possibly unsupported tz) verbatim
                    # for uncertain items instead of guessing.
                    start = item.start_at
            else:
                start = None
            if item.end_at is not None:
                try:
                    end = normalize_datetime(item.end_at, item.tz)
                except ValueError:
                    end = item.end_at
            else:
                end = None
            item = replace(item, start_at=start, end_at=end)
            if item.end_at is not None and item.start_at is not None:
                if datetime.fromisoformat(item.end_at) < datetime.fromisoformat(
                    item.start_at
                ):
                    raise ScheduleValidationError(
                        f"end_at {item.end_at} is before start_at {item.start_at}"
                    )

        # Status transitions: terminal states never revert silently.
        if item.status is ItemStatus.COMPLETED and item.kind is not ItemKind.TASK:
            raise ScheduleValidationError("events cannot be completed")

        return item

    def _get_locked(self, item_id: str) -> TaskItem:
        item = self._repo.find_by_id(item_id)
        if item is None:
            raise ScheduleNotFoundError(f"item not found: {item_id}")
        return item

    @staticmethod
    def _changed_fields(
        before: TaskItem, after: TaskItem, requested: Any
    ) -> List[str]:
        """Names of fields whose value actually changed (requested ∩ changed)."""
        b, a = item_to_dict(before), item_to_dict(after)
        return sorted(f for f in requested if b.get(f) != a.get(f))
