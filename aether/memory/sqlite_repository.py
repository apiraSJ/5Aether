"""SQLiteRepository — SQLite-backed memory storage with WAL + FTS5 + R-Tree.

Architecture:
    MemoryManager → MemoryRepository (abstract) → SQLiteRepository

Responsibilities:
    - Database lifecycle (open, close, vacuum)
    - CRUD operations for all memory types
    - FTS5 full-text search (semantic, episodic)
    - R-Tree spatial queries (nearest neighbor, within radius)
    - TTL-based expiration cleanup
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aether.memory.models import MemoryRecord, MemoryType, QueryFilter, RecallResult, SpatialRecord
from aether.memory.schema import SCHEMA_SQL

logger = logging.getLogger("Aether.SQLiteRepository")

_MEMORY_TABLES = {
    MemoryType.WORKING: "working",
    MemoryType.SEMANTIC: "semantic",
    MemoryType.EPISODIC: "episodic",
    MemoryType.SPATIAL: "spatial",
}


class SQLiteRepository:
    """SQLite-backed memory repository.

    Thread-safe via RLock. WAL mode for concurrent reads.
    FTS5 for full-text search. R-Tree for spatial queries.
    """

    def __init__(self, db_path: str = "data/memory.db") -> None:
        self._db_path = Path(db_path)
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._open = False

    def open(self) -> None:
        """Open database connection and initialize schema."""
        if self._open:
            return

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        with self._lock:
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()

        self._open = True
        logger.info("Memory DB opened: %s", self._db_path)

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None
            self._open = False
        logger.debug("Memory DB closed")

    @property
    def is_open(self) -> bool:
        return self._open

    # ── CRUD ───────────────────────────────────────────────────────

    def store(
        self,
        memory_type: MemoryType,
        key: str,
        value: Any = None,
        context: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[float] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        confidence: float = 1.0,
        label: str = "",
        created_at: Optional[float] = None,
    ) -> str:
        """Store a memory record. Returns the record ID.

        Args:
            memory_type: Type of memory (semantic, episodic, spatial, working)
            key: Primary lookup key
            value: JSON-serializable payload
            context: Optional metadata dict
            ttl_seconds: Time-to-live in seconds (None = infinite)
            x, y, z: 3D position (spatial only)
            confidence: Detection confidence (spatial only)
            label: Object label (spatial only)
            created_at: Explicit wall-clock timestamp (None = now)
        """
        record_id = str(uuid.uuid4())
        now = time.time() if created_at is None else created_at
        value_json = json.dumps(value) if value is not None else None
        context_json = json.dumps(context or {})

        with self._lock:
            self._ensure_open()
            table = _MEMORY_TABLES[memory_type]

            if memory_type == MemoryType.SPATIAL:
                cursor = self._conn.execute(
                    f"""INSERT INTO {table}
                        (id, key, label, value, context, x, y, z, confidence,
                         created_at, updated_at, access_count, ttl_seconds)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
                    (record_id, key, label, value_json, context_json,
                     x or 0.0, y or 0.0, z or 0.0, confidence,
                     now, now, ttl_seconds),
                )
                # Update R-Tree index
                self._conn.execute(
                    """INSERT INTO spatial_rtree (id, min_x, max_x, min_y, max_y, min_z, max_z)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (cursor.lastrowid, x or 0.0, x or 0.0,
                     y or 0.0, y or 0.0, z or 0.0, z or 0.0),
                )
            else:
                self._conn.execute(
                    f"""INSERT INTO {table}
                        (id, key, value, context, created_at, updated_at,
                         access_count, ttl_seconds)
                        VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                    (record_id, key, value_json, context_json, now, now, ttl_seconds),
                )

            self._conn.commit()

        return record_id

    def recall(self, key: str, memory_type: Optional[MemoryType] = None) -> RecallResult:
        """Recall a memory record by key.

        Args:
            key: Primary lookup key
            memory_type: Optional type filter

        Returns:
            RecallResult with matching records
        """
        t0 = time.perf_counter()
        with self._lock:
            self._ensure_open()
            records = []

            if memory_type:
                tables = [_MEMORY_TABLES[memory_type]]
            else:
                tables = list(_MEMORY_TABLES.values())

            for table in tables:
                rows = self._conn.execute(
                    f"SELECT * FROM {table} WHERE key = ? ORDER BY updated_at DESC LIMIT 20",
                    (key,),
                ).fetchall()
                for row in rows:
                    records.append(self._row_to_record(row, table))
                    # Increment access count
                    self._conn.execute(
                        f"UPDATE {table} SET access_count = access_count + 1 WHERE id = ?",
                        (row["id"],),
                    )

            self._conn.commit()

        elapsed = (time.perf_counter() - t0) * 1000.0
        return RecallResult(
            found=len(records) > 0,
            records=records,
            total=len(records),
            query_time_ms=elapsed,
        )

    def search(self, query: str, filter_obj: Optional[QueryFilter] = None) -> RecallResult:
        """Full-text search across semantic and episodic memory.

        Uses FTS5 for fast text matching.

        Args:
            query: Search text
            filter_obj: Optional query filter

        Returns:
            RecallResult with matching records
        """
        t0 = time.perf_counter()
        f = filter_obj or QueryFilter()
        records = []

        with self._lock:
            self._ensure_open()
            tables = ["semantic", "episodic"]

            for table in tables:
                fts_table = f"{table}_fts"
                sql = (
                    f"SELECT {table}.* FROM {fts_table} "
                    f"JOIN {table} ON {fts_table}.rowid = {table}.rowid "
                    f"WHERE {fts_table} MATCH ? "
                    f"ORDER BY rank "
                    f"LIMIT ? OFFSET ?"
                )
                try:
                    rows = self._conn.execute(sql, (query, f.limit, f.offset)).fetchall()
                    for row in rows:
                        records.append(self._row_to_record(row, table))
                except sqlite3.OperationalError as e:
                    logger.warning("FTS5 search error: %s", e)

        elapsed = (time.perf_counter() - t0) * 1000.0
        return RecallResult(
            found=len(records) > 0,
            records=records,
            total=len(records),
            query_time_ms=elapsed,
        )

    def recall_nearby(
        self,
        x: float,
        y: float,
        z: float,
        radius_meters: float = 5.0,
        label: Optional[str] = None,
        limit: int = 20,
    ) -> RecallResult:
        """Find spatial records near a 3D position.

        Uses R-Tree index for efficient spatial queries.

        Args:
            x, y, z: Query position
            radius_meters: Search radius
            label: Optional object label filter
            limit: Maximum results

        Returns:
            RecallResult with matching SpatialRecords
        """
        t0 = time.perf_counter()

        with self._lock:
            self._ensure_open()
            sql = (
                "SELECT spatial.* FROM spatial "
                "JOIN spatial_rtree ON spatial.rowid = spatial_rtree.id "
                "WHERE spatial_rtree.min_x >= ? AND spatial_rtree.max_x <= ? "
                "AND spatial_rtree.min_y >= ? AND spatial_rtree.max_y <= ? "
                "AND spatial_rtree.min_z >= ? AND spatial_rtree.max_z <= ? "
            )
            params = [
                x - radius_meters, x + radius_meters,
                y - radius_meters, y + radius_meters,
                z - radius_meters, z + radius_meters,
            ]

            if label:
                sql += " AND spatial.label = ?"
                params.append(label)

            sql += " ORDER BY spatial.updated_at DESC LIMIT ?"
            params.append(limit)

            rows = self._conn.execute(sql, params).fetchall()
            records = [self._row_to_spatial(row) for row in rows]

        elapsed = (time.perf_counter() - t0) * 1000.0
        return RecallResult(
            found=len(records) > 0,
            records=records,  # type: ignore
            total=len(records),
            query_time_ms=elapsed,
        )

    def update(
        self,
        record_id: str,
        value: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update a memory record by ID.

        Args:
            record_id: Record UUID
            value: New value (None = keep existing)
            context: New context (None = keep existing)

        Returns:
            True if record was found and updated
        """
        now = time.time()
        with self._lock:
            self._ensure_open()
            for table in _MEMORY_TABLES.values():
                updates = ["updated_at = ?"]
                params: List[Any] = [now]

                if value is not None:
                    updates.append("value = ?")
                    params.append(json.dumps(value))
                if context is not None:
                    updates.append("context = ?")
                    params.append(json.dumps(context))

                params.append(record_id)
                sql = f"UPDATE {table} SET {', '.join(updates)} WHERE id = ?"
                cursor = self._conn.execute(sql, params)
                if cursor.rowcount > 0:
                    self._conn.commit()
                    return True

        return False

    def forget(self, key: str, memory_type: Optional[MemoryType] = None) -> int:
        """Delete memory records by key.

        Args:
            key: Primary lookup key
            memory_type: Optional type filter

        Returns:
            Number of records deleted
        """
        total = 0
        with self._lock:
            self._ensure_open()
            if memory_type:
                tables = [_MEMORY_TABLES[memory_type]]
            else:
                tables = list(_MEMORY_TABLES.values())

            for table in tables:
                if table == "spatial":
                    # Get rowids before deleting (needed for R-Tree cleanup)
                    rows = self._conn.execute(
                        "SELECT rowid FROM spatial WHERE key = ?", (key,),
                    ).fetchall()
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE key = ?", (key,),
                    )
                    for row in rows:
                        self._conn.execute(
                            "DELETE FROM spatial_rtree WHERE id = ?", (row["rowid"],),
                        )
                else:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE key = ?", (key,),
                    )
                total += cursor.rowcount

            self._conn.commit()

        return total

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        """Fetch a single record by ID across all memory tables."""
        with self._lock:
            self._ensure_open()
            for table in _MEMORY_TABLES.values():
                row = self._conn.execute(
                    f"SELECT * FROM {table} WHERE id = ? LIMIT 1", (record_id,),
                ).fetchone()
                if row:
                    return self._row_to_record(row, table)
        return None

    def delete(self, record_id: str) -> bool:
        """Delete a single record by ID. Returns True if found and deleted."""
        with self._lock:
            self._ensure_open()
            for table in _MEMORY_TABLES.values():
                if table == "spatial":
                    rows = self._conn.execute(
                        "SELECT rowid FROM spatial WHERE id = ?", (record_id,),
                    ).fetchall()
                    cursor = self._conn.execute(
                        "DELETE FROM spatial WHERE id = ?", (record_id,),
                    )
                    for row in rows:
                        self._conn.execute(
                            "DELETE FROM spatial_rtree WHERE id = ?", (row["rowid"],),
                        )
                else:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE id = ?", (record_id,),
                    )
                if cursor.rowcount > 0:
                    self._conn.commit()
                    return True
        return False

    def list_recent(
        self,
        limit: int = 10,
        memory_type: Optional[MemoryType] = None,
    ) -> RecallResult:
        """List the most recently updated records (semantic + episodic).

        Args:
            limit: Maximum number of records
            memory_type: Optional type filter

        Returns:
            RecallResult ordered by updated_at DESC
        """
        t0 = time.perf_counter()
        with self._lock:
            self._ensure_open()
            if memory_type:
                tables = [_MEMORY_TABLES[memory_type]]
            else:
                tables = ["semantic", "episodic"]

            records = []
            for table in tables:
                rows = self._conn.execute(
                    f"SELECT * FROM {table} ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                records.extend(self._row_to_record(r, table) for r in rows)

        records.sort(key=lambda r: r.updated_at, reverse=True)
        records = records[:limit]

        elapsed = (time.perf_counter() - t0) * 1000.0
        return RecallResult(
            found=len(records) > 0,
            records=records,
            total=len(records),
            query_time_ms=elapsed,
        )

    def list_pinned(
        self,
        limit: int = 20,
        memory_type: Optional[MemoryType] = None,
    ) -> RecallResult:
        """List pinned records (context['pinned'] == true).

        Args:
            limit: Maximum number of records
            memory_type: Optional type filter

        Returns:
            RecallResult ordered by updated_at DESC
        """
        with self._lock:
            self._ensure_open()
            if memory_type:
                tables = [_MEMORY_TABLES[memory_type]]
            else:
                tables = ["semantic", "episodic"]

            records = []
            for table in tables:
                try:
                    rows = self._conn.execute(
                        "SELECT * FROM {table} "
                        "WHERE json_extract(context, '$.pinned') = 1 "
                        "ORDER BY updated_at DESC LIMIT ?".format(table=table),
                        (limit,),
                    ).fetchall()
                    records.extend(self._row_to_record(r, table) for r in rows)
                except sqlite3.OperationalError as e:
                    logger.warning("list_pinned failed on '%s': %s", table, e)

        records.sort(key=lambda r: r.updated_at, reverse=True)
        records = records[:limit]

        return RecallResult(
            found=len(records) > 0,
            records=records,
            total=len(records),
        )

    def set_pinned(self, record_id: str, pinned: bool) -> bool:
        """Set the pinned flag on a record. Returns True if found and updated."""
        with self._lock:
            self._ensure_open()
            for table in _MEMORY_TABLES.values():
                row = self._conn.execute(
                    f"SELECT context FROM {table} WHERE id = ? LIMIT 1", (record_id,),
                ).fetchone()
                if not row:
                    continue
                ctx = json.loads(row["context"]) if row["context"] else {}
                ctx["pinned"] = bool(pinned)
                self._conn.execute(
                    "UPDATE {table} SET context = ?, updated_at = ? WHERE id = ?".format(table=table),
                    (json.dumps(ctx), time.time(), record_id),
                )
                self._conn.commit()
                return True
        return False

    def seed_demo(self, records: List[Dict[str, Any]], created_at: Optional[float] = None) -> int:
        """Store demo records into the semantic table.

        Args:
            records: List of dicts with title, summary, content, tags,
                importance, source, pinned, age_days
            created_at: Base wall-clock timestamp (None = now); each record
                is stored age_days in the past.

        Returns:
            Number of records stored
        """
        if created_at is None:
            created_at = time.time()

        def days_ago(days: float) -> float:
            return created_at - days * 24 * 60 * 60

        stored = 0
        with self._lock:
            self._ensure_open()
            for i, mem in enumerate(records):
                context: Dict[str, Any] = {
                    "title": mem.get("title", ""),
                    "summary": mem.get("summary", ""),
                    "content": mem.get("content", ""),
                    "tags": mem.get("tags", []),
                    "importance": mem.get("importance", 0),
                    "source": mem.get("source", ""),
                    "pinned": bool(mem.get("pinned", False)),
                }
                key = mem.get("key") or f"demo-{i:02d}-{mem.get('title', '').lower().replace(' ', '-')}"
                self.store(
                    memory_type=MemoryType.SEMANTIC,
                    key=key,
                    value={"title": context["title"], "summary": context["summary"]},
                    context=context,
                    created_at=days_ago(mem.get("age_days", 0)),
                )
                stored += 1
        return stored

    def expire_stale(self) -> int:
        """Delete all expired records based on TTL.

        Returns:
            Number of records deleted
        """
        now = time.time()
        total = 0

        with self._lock:
            self._ensure_open()
            for table in _MEMORY_TABLES.values():
                if table == "spatial":
                    rows = self._conn.execute(
                        "SELECT rowid FROM spatial WHERE ttl_seconds IS NOT NULL AND ? - created_at > ttl_seconds",
                        (now,),
                    ).fetchall()
                    cursor = self._conn.execute(
                        "DELETE FROM spatial WHERE ttl_seconds IS NOT NULL AND ? - created_at > ttl_seconds",
                        (now,),
                    )
                    for row in rows:
                        self._conn.execute(
                            "DELETE FROM spatial_rtree WHERE id = ?", (row["rowid"],),
                        )
                else:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE ttl_seconds IS NOT NULL AND ? - created_at > ttl_seconds",
                        (now,),
                    )
                total += cursor.rowcount

            self._conn.commit()

        if total > 0:
            logger.debug("Expired %d stale memory records", total)
        return total

    def count(self, memory_type: Optional[MemoryType] = None) -> int:
        """Count records in memory store."""
        with self._lock:
            self._ensure_open()
            if memory_type:
                tables = [_MEMORY_TABLES[memory_type]]
            else:
                tables = list(_MEMORY_TABLES.values())

            result = 0
            for table in tables:
                row = self._conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
                result += row["cnt"]
            return result

    def list_keys(self, memory_type: Optional[MemoryType] = None) -> List[str]:
        """List all unique keys in memory store."""
        with self._lock:
            self._ensure_open()
            if memory_type:
                tables = [_MEMORY_TABLES[memory_type]]
            else:
                tables = list(_MEMORY_TABLES.values())

            keys: List[str] = []
            for table in tables:
                rows = self._conn.execute(
                    f"SELECT DISTINCT key FROM {table} ORDER BY key"
                ).fetchall()
                keys.extend(row["key"] for row in rows)
            return sorted(set(keys))

    def vacuum(self) -> None:
        """Vacuum database to reclaim space."""
        with self._lock:
            self._ensure_open()
            self._conn.execute("VACUUM")
        logger.info("Memory DB vacuumed")

    # ── Internal ───────────────────────────────────────────────────

    def _ensure_open(self) -> None:
        if not self._open or not self._conn:
            raise RuntimeError("Memory repository not opened. Call open() first.")

    def _row_to_record(self, row: sqlite3.Row, table: str) -> MemoryRecord:
        if table == "spatial":
            return self._row_to_spatial(row)
        return MemoryRecord(
            id=row["id"],
            memory_type=table,
            key=row["key"],
            value=json.loads(row["value"]) if row["value"] else None,
            context=json.loads(row["context"]) if row["context"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            access_count=row["access_count"],
            ttl_seconds=row["ttl_seconds"],
        )

    def _row_to_spatial(self, row: sqlite3.Row) -> SpatialRecord:
        return SpatialRecord(
            id=row["id"],
            memory_type="spatial",
            key=row["key"],
            value=json.loads(row["value"]) if row["value"] else None,
            context=json.loads(row["context"]) if row["context"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            access_count=row["access_count"],
            ttl_seconds=row["ttl_seconds"],
            x=row["x"],
            y=row["y"],
            z=row["z"],
            confidence=row["confidence"],
            label=row["label"],
        )
