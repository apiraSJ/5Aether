"""Phase 1 tests — schema + migrations for data/tasks.db.

Covers the Phase 1 acceptance criteria:
    - migration is safely re-runnable (idempotent) and never downgrades
    - WAL + foreign keys enabled
    - all five tables exist with defensive CHECK constraints
    - data/memory.db (Memory Core) is never touched
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aether.task.migrations import (
    CURRENT_VERSION,
    MIGRATIONS,
    MigrationError,
    migrate,
    user_version,
)
from aether.task.repository import SqliteScheduleRepository
from aether.task.schema import SCHEMA_SQL_V1


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "tasks.db")


@pytest.fixture
def repo(db_path):
    r = SqliteScheduleRepository(db_path)
    r.open()
    yield r
    r.close()


TABLES = {"items", "evidence", "item_history", "review_queue", "import_batches"}


def _table_names(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


class TestFreshMigration:
    def test_creates_all_tables(self, repo):
        tables = _table_names(repo._conn)
        assert TABLES <= tables

    def test_user_version_is_current(self, repo):
        assert user_version(repo._conn) == CURRENT_VERSION == 1

    def test_wal_enabled(self, repo):
        mode = repo._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_foreign_keys_enabled(self, repo):
        # PRAGMA foreign_keys is per-connection; check the live connection.
        fk = repo._conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

    def test_indexes_exist(self, repo):
        names = {
            r[0]
            for r in repo._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        assert {
            "idx_items_kind",
            "idx_items_status",
            "idx_items_due_date",
            "idx_items_start_at",
            "idx_evidence_item",
            "idx_history_item",
            "idx_review_state",
        } <= names


class TestMigrationIdempotency:
    def test_rerun_is_noop(self, repo):
        before = _table_names(repo._conn)
        assert migrate(repo._conn) == 1
        assert migrate(repo._conn) == 1
        assert _table_names(repo._conn) == before

    def test_reopen_reruns_safely(self, db_path):
        for _ in range(3):
            r = SqliteScheduleRepository(db_path)
            r.open()
            assert user_version(r._conn) == 1
            r.close()

    def test_partial_ddl_then_migrate_recovers(self, db_path):
        """Crash between DDL and version bump → re-running migrate heals."""
        conn = sqlite3.connect(db_path)
        conn.executescript(SCHEMA_SQL_V1)  # DDL applied, version still 0
        assert user_version(conn) == 0
        assert migrate(conn) == 1
        conn.close()

    def test_no_downgrade_refused(self, repo):
        repo._conn.execute("PRAGMA user_version = 99")
        with pytest.raises(MigrationError, match="newer than supported"):
            migrate(repo._conn)
        # Version must be left untouched (never downgraded).
        assert user_version(repo._conn) == 99

    def test_migration_list_is_well_formed(self):
        targets = [t for t, _ in MIGRATIONS]
        assert targets == sorted(set(targets))
        assert targets[0] == 1
        assert targets[-1] == CURRENT_VERSION

    def test_empty_migrations_refused(self, repo, monkeypatch):
        import aether.task.migrations as m

        monkeypatch.setattr(m, "MIGRATIONS", [])
        with pytest.raises(MigrationError, match="empty"):
            m.migrate(repo._conn)

    def test_unordered_migrations_refused(self, repo, monkeypatch):
        import aether.task.migrations as m

        monkeypatch.setattr(m, "MIGRATIONS", [(2, "SELECT 1;"), (1, "SELECT 1;")])
        with pytest.raises(MigrationError, match="ascending"):
            m.migrate(repo._conn)

    def test_first_must_be_version_1(self, repo, monkeypatch):
        import aether.task.migrations as m

        monkeypatch.setattr(m, "MIGRATIONS", [(3, "SELECT 1;")])
        with pytest.raises(MigrationError, match="version 1"):
            m.migrate(repo._conn)


class TestSchemaConstraints:
    """SQL CHECK backstops (service validation is the primary gate)."""

    def _insert(self, repo, **kw):
        defaults = dict(
            id="item_c",
            kind="task",
            title="t",
            description="",
            status="pending",
            internal_status="confirmed",
            due_date=None,
            start_at=None,
            end_at=None,
            all_day=0,
            tz="Asia/Bangkok",
            owner=None,
            source="manual",
            created_at=1.0,
            updated_at=1.0,
        )
        defaults.update(kw)
        cols = ", ".join(defaults)
        marks = ", ".join("?" for _ in defaults)
        repo._conn.execute(
            f"INSERT INTO items ({cols}) VALUES ({marks})",
            tuple(defaults.values()),
        )

    def test_rejects_bad_kind(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(repo, kind="deadline")

    def test_rejects_empty_title(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(repo, title="   ")

    def test_rejects_event_without_start(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(repo, kind="event")

    def test_rejects_event_with_due_date(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(
                repo, kind="event", start_at="2026-10-20T10:00:00+07:00",
                due_date="2026-10-20",
            )

    def test_rejects_task_with_all_day(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(repo, all_day=1)

    def test_rejects_bad_status(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(repo, status="archived")

    def test_rejects_bad_internal_status(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(repo, internal_status="maybe")

    def test_rejects_all_day_with_datetime_start(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(
                repo, kind="event", all_day=1,
                start_at="2026-10-20T10:00:00+07:00",
            )

    def test_rejects_end_without_start(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(repo, end_at="2026-10-20T11:00:00+07:00")

    def test_rejects_overlong_due_date(self, repo):
        with pytest.raises(sqlite3.IntegrityError):
            self._insert(repo, due_date="2026-10-20T00:00")

    def test_accepts_valid_event_all_day(self, repo):
        self._insert(
            repo, kind="event", all_day=1,
            start_at="2026-10-20", end_at="2026-10-21",
        )
        assert repo._conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


class TestMemoryCoreIsolation:
    def test_migrate_does_not_create_memory_tables(self, db_path):
        conn = sqlite3.connect(db_path)
        migrate(conn)
        tables = _table_names(conn)
        assert not ({"semantic", "episodic", "working", "spatial"} & tables)
        conn.close()

    def test_repo_touches_only_tasks_db(self, tmp_path):
        """Full service session must not modify memory.db bytes."""
        import hashlib

        mem_path = tmp_path / "memory.db"
        mem_conn = sqlite3.connect(str(mem_path))
        mem_conn.execute("CREATE TABLE semantic (id TEXT PRIMARY KEY)")
        mem_conn.execute("INSERT INTO semantic VALUES ('keep')")
        mem_conn.commit()
        mem_conn.close()
        before = hashlib.sha256(mem_path.read_bytes()).hexdigest()

        r = SqliteScheduleRepository(str(tmp_path / "tasks.db"))
        r.open()
        r._conn.execute(
            "INSERT INTO items (id, kind, title, created_at, updated_at) "
            "VALUES ('item_iso', 'task', 'x', 1.0, 1.0)"
        )
        r.close()

        after = hashlib.sha256(mem_path.read_bytes()).hexdigest()
        assert before == after
