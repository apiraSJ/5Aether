"""SqliteScheduleRepository — SQLite storage for Aether Mark 1 schedule data.

Architecture:
    ScheduleService → IScheduleRepository → SqliteScheduleRepository → data/tasks.db

Mirrors the Memory Core pattern (SQLiteRepository): WAL, foreign_keys=ON,
RLock thread safety, explicit transaction control. Schema/migrations live
in aether.task.schema / aether.task.migrations.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from aether.core.interfaces.i_schedule_repository import IScheduleRepository
from aether.task.migrations import migrate
from aether.task.models import (
    Evidence,
    HistoryAction,
    HistoryEntry,
    ImportBatch,
    InternalStatus,
    ItemKind,
    ItemStatus,
    ReviewEntry,
    ReviewState,
    TaskItem,
)

logger = logging.getLogger("Aether.task.repository")

_DEFAULT_DB_PATH = "data/tasks.db"


class SqliteScheduleRepository(IScheduleRepository):
    """SQLite-backed schedule repository (items, evidence, history, review, batches)."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._open = False
        self._txn_depth = 0

    # ── Lifecycle ──────────────────────────────────────────────────

    def open(self) -> None:
        """Open database, enable WAL + FK, run migrations."""
        if self._open:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            migrate(self._conn)
        self._open = True
        logger.info("Tasks DB opened: %s", self._db_path)

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
            self._open = False
        logger.debug("Tasks DB closed")

    @property
    def is_open(self) -> bool:
        return self._open

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Explicit write transaction. Re-entrant: joins an open one."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            if self._txn_depth > 0:
                self._txn_depth += 1
                try:
                    yield self._conn
                finally:
                    self._txn_depth -= 1
                return
            self._conn.execute("BEGIN IMMEDIATE")
            self._txn_depth = 1
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            finally:
                self._txn_depth = 0

    # ── Items ──────────────────────────────────────────────────────

    def save(self, item: TaskItem) -> bool:
        """Insert or update one item."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            self._conn.execute(
                """
                INSERT INTO items (
                    id, kind, title, description, status, internal_status,
                    due_date, start_at, end_at, all_day, tz, owner, source,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind = excluded.kind,
                    title = excluded.title,
                    description = excluded.description,
                    status = excluded.status,
                    internal_status = excluded.internal_status,
                    due_date = excluded.due_date,
                    start_at = excluded.start_at,
                    end_at = excluded.end_at,
                    all_day = excluded.all_day,
                    tz = excluded.tz,
                    owner = excluded.owner,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    item.id,
                    item.kind.value,
                    item.title,
                    item.description,
                    item.status.value,
                    item.internal_status.value,
                    item.due_date,
                    item.start_at,
                    item.end_at,
                    1 if item.all_day else 0,
                    item.tz,
                    item.owner,
                    item.source,
                    item.created_at,
                    item.updated_at,
                ),
            )
            return True

    def find_by_id(self, item_id: str) -> Optional[TaskItem]:
        """Find one item by id."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            row = self._conn.execute(
                "SELECT * FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            return self._row_to_item(row) if row else None

    def find_all(
        self,
        kind: Optional[ItemKind] = None,
        status: Optional[ItemStatus] = None,
    ) -> List[TaskItem]:
        """List items, optionally filtered by kind and/or status."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            query = "SELECT * FROM items"
            clauses: List[str] = []
            params: List[object] = []
            if kind is not None:
                clauses.append("kind = ?")
                params.append(kind.value)
            if status is not None:
                clauses.append("status = ?")
                params.append(status.value)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at ASC, id ASC"
            rows = self._conn.execute(query, params).fetchall()
            return [self._row_to_item(r) for r in rows]

    def delete(self, item_id: str) -> bool:
        """Delete one item (evidence + review cascade; history survives)."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            cur = self._conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
            return cur.rowcount > 0

    def count(self) -> int:
        """Total number of items."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            row = self._conn.execute("SELECT COUNT(*) FROM items").fetchone()
            return int(row[0])

    # ── Evidence ───────────────────────────────────────────────────

    def add_evidence(self, evidence: List[Evidence]) -> int:
        """Attach evidence rows to an item. Returns rows written."""
        if not evidence:
            return 0
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            self._conn.executemany(
                """
                INSERT INTO evidence (
                    id, item_id, source, source_ref, excerpt, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        e.id,
                        e.item_id,
                        e.source,
                        e.source_ref,
                        e.excerpt,
                        e.confidence,
                        e.created_at,
                    )
                    for e in evidence
                ],
            )
            return len(evidence)

    def get_evidence(self, item_id: str) -> List[Evidence]:
        """Evidence rows for one item, oldest first."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            rows = self._conn.execute(
                "SELECT * FROM evidence WHERE item_id = ? ORDER BY created_at ASC, id ASC",
                (item_id,),
            ).fetchall()
            return [
                Evidence(
                    id=r["id"],
                    item_id=r["item_id"],
                    source=r["source"],
                    source_ref=r["source_ref"],
                    excerpt=r["excerpt"],
                    confidence=r["confidence"],
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    # ── History (append-only) ──────────────────────────────────────

    def append_history(self, entry: HistoryEntry) -> bool:
        """Append one audit record."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            self._conn.execute(
                """
                INSERT INTO item_history (
                    id, item_id, action, before_json, after_json,
                    changed_fields, note, actor, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.item_id,
                    entry.action.value,
                    json.dumps(entry.before, ensure_ascii=False) if entry.before is not None else None,
                    json.dumps(entry.after, ensure_ascii=False) if entry.after is not None else None,
                    json.dumps(entry.changed_fields, ensure_ascii=False),
                    entry.note,
                    entry.actor,
                    entry.created_at,
                ),
            )
            return True

    def get_history(self, item_id: str, limit: int = 100) -> List[HistoryEntry]:
        """Audit records for one item, newest first, capped at limit."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            rows = self._conn.execute(
                """
                SELECT * FROM item_history WHERE item_id = ?
                ORDER BY created_at DESC, id DESC LIMIT ?
                """,
                (item_id, limit),
            ).fetchall()
            return [self._row_to_history(r) for r in rows]

    # ── Review queue ───────────────────────────────────────────────

    def enqueue_review(self, entry: ReviewEntry) -> bool:
        """Add one pending review row (unique pending row per item)."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            self._conn.execute(
                """
                INSERT INTO review_queue (
                    id, item_id, reason, payload, confidence, state,
                    created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.item_id,
                    entry.reason,
                    json.dumps(entry.payload, ensure_ascii=False),
                    entry.confidence,
                    entry.state.value,
                    entry.created_at,
                    entry.resolved_at,
                ),
            )
            return True

    def list_reviews(
        self, state: Optional[ReviewState] = None
    ) -> List[ReviewEntry]:
        """Review rows, optionally filtered by state (None = all states)."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            if state is None:
                rows = self._conn.execute(
                    "SELECT * FROM review_queue ORDER BY created_at ASC, id ASC"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM review_queue WHERE state = ? "
                    "ORDER BY created_at ASC, id ASC",
                    (state.value,),
                ).fetchall()
            return [self._row_to_review(r) for r in rows]

    def resolve_review(
        self, review_id: str, state: ReviewState, resolved_at: float
    ) -> bool:
        """Resolve one pending review row. Returns False if not pending."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            cur = self._conn.execute(
                """
                UPDATE review_queue SET state = ?, resolved_at = ?
                WHERE id = ? AND state = 'pending'
                """,
                (state.value, resolved_at, review_id),
            )
            return cur.rowcount > 0

    # ── Import batches ─────────────────────────────────────────────

    def record_batch(self, batch: ImportBatch) -> bool:
        """Record one import batch. Fails on duplicate content_hash."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            self._conn.execute(
                """
                INSERT INTO import_batches (
                    id, source, format_version, content_hash, item_count,
                    stats, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch.id,
                    batch.source,
                    batch.format_version,
                    batch.content_hash,
                    batch.item_count,
                    json.dumps(batch.stats, ensure_ascii=False),
                    batch.imported_at,
                ),
            )
            return True

    def find_batch_by_hash(self, content_hash: str) -> Optional[ImportBatch]:
        """Find an import batch by content hash (re-import dedupe)."""
        with self._lock:
            self._ensure_open()
            assert self._conn is not None
            row = self._conn.execute(
                "SELECT * FROM import_batches WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
            if not row:
                return None
            return ImportBatch(
                id=row["id"],
                source=row["source"],
                format_version=row["format_version"],
                content_hash=row["content_hash"],
                item_count=row["item_count"],
                stats=json.loads(row["stats"]),
                imported_at=row["imported_at"],
            )

    # ── Row mappers ────────────────────────────────────────────────

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> TaskItem:
        return TaskItem(
            id=row["id"],
            kind=ItemKind(row["kind"]),
            title=row["title"],
            description=row["description"],
            status=ItemStatus(row["status"]),
            internal_status=InternalStatus(row["internal_status"]),
            due_date=row["due_date"],
            start_at=row["start_at"],
            end_at=row["end_at"],
            all_day=bool(row["all_day"]),
            tz=row["tz"],
            owner=row["owner"],
            source=row["source"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_history(row: sqlite3.Row) -> HistoryEntry:
        return HistoryEntry(
            id=row["id"],
            item_id=row["item_id"],
            action=HistoryAction(row["action"]),
            before=json.loads(row["before_json"]) if row["before_json"] else None,
            after=json.loads(row["after_json"]) if row["after_json"] else None,
            changed_fields=json.loads(row["changed_fields"]),
            note=row["note"],
            actor=row["actor"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_review(row: sqlite3.Row) -> ReviewEntry:
        return ReviewEntry(
            id=row["id"],
            item_id=row["item_id"],
            reason=row["reason"],
            payload=json.loads(row["payload"]),
            confidence=row["confidence"],
            state=ReviewState(row["state"]),
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )

    def _ensure_open(self) -> None:
        if not self._open or self._conn is None:
            raise RuntimeError("ScheduleRepository is not open — call open() first")
