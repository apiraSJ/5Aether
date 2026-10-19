"""IScheduleRepository — persistence contracts for Aether Mark 1.

This is the Mark 1 L2 boundary for `data/tasks.db` (items + evidence +
item_history + review_queue + import_batches). It complements — and must
never be confused with — the Memory Core contracts in
`i_memory_repository.py` (ITaskRepository there refers to the legacy
execution-task model in aether/domain/task.py and stays untouched).

Implementations:
    SqliteScheduleRepository — production (aether/task/repository.py)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:  # avoid circular import: aether.task imports this module
    from aether.task.models import (
        Evidence,
        HistoryEntry,
        ImportBatch,
        ItemKind,
        ItemStatus,
        ReviewEntry,
        ReviewState,
        TaskItem,
    )


class IScheduleRepository(ABC):
    """CRUD + audit + review for schedule items (Mark 1)."""

    # ── Lifecycle ──────────────────────────────────────────────────

    @abstractmethod
    def open(self) -> None:
        """Open the database, run migrations, enable WAL + FK."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""
        ...

    @property
    @abstractmethod
    def is_open(self) -> bool:
        """True while the connection is usable."""
        ...

    @abstractmethod
    def transaction(self) -> AbstractContextManager[None]:
        """Explicit write transaction (BEGIN IMMEDIATE … COMMIT/ROLLBACK).

        Mutations that must be atomic together (item write + history
        append) are executed inside this context manager. Re-entrant:
        joining an open transaction is a no-op.
        """
        ...

    # ── Items ──────────────────────────────────────────────────────

    @abstractmethod
    def save(self, item: TaskItem) -> bool:
        """Insert or update one item. Returns True on success."""
        ...

    @abstractmethod
    def find_by_id(self, item_id: str) -> Optional[TaskItem]:
        """Find one item by id."""
        ...

    @abstractmethod
    def find_all(
        self,
        kind: Optional[ItemKind] = None,
        status: Optional[ItemStatus] = None,
    ) -> List[TaskItem]:
        """List items, optionally filtered by kind and/or status."""
        ...

    @abstractmethod
    def delete(self, item_id: str) -> bool:
        """Delete one item (evidence + review cascade; history survives)."""
        ...

    @abstractmethod
    def count(self) -> int:
        """Total number of items."""
        ...

    # ── Evidence ───────────────────────────────────────────────────

    @abstractmethod
    def add_evidence(self, evidence: List[Evidence]) -> int:
        """Attach evidence rows to an item. Returns rows written."""
        ...

    @abstractmethod
    def get_evidence(self, item_id: str) -> List[Evidence]:
        """Evidence rows for one item, oldest first."""
        ...

    # ── History (append-only) ──────────────────────────────────────

    @abstractmethod
    def append_history(self, entry: HistoryEntry) -> bool:
        """Append one audit record. Returns True on success."""
        ...

    @abstractmethod
    def get_history(self, item_id: str, limit: int = 100) -> List[HistoryEntry]:
        """Audit records for one item, newest first, capped at limit."""
        ...

    # ── Review queue ───────────────────────────────────────────────

    @abstractmethod
    def enqueue_review(self, entry: ReviewEntry) -> bool:
        """Add one pending review row. Fails if item already pending."""
        ...

    @abstractmethod
    def list_reviews(
        self, state: Optional[ReviewState] = None
    ) -> List[ReviewEntry]:
        """Review rows, optionally filtered by state (None = all states)."""
        ...

    @abstractmethod
    def resolve_review(
        self, review_id: str, state: ReviewState, resolved_at: float
    ) -> bool:
        """Resolve one pending review row. Returns False if not pending."""
        ...

    # ── Import batches ─────────────────────────────────────────────

    @abstractmethod
    def record_batch(self, batch: ImportBatch) -> bool:
        """Record one import batch. Fails on duplicate content_hash."""
        ...

    @abstractmethod
    def find_batch_by_hash(self, content_hash: str) -> Optional[ImportBatch]:
        """Find an import batch by content hash (re-import dedupe)."""
        ...
