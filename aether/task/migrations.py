"""Stepwise schema migrations for `data/tasks.db` via PRAGMA user_version.

Contract (Phase 1 acceptance):
    - Migrations are append-only: never edit or remove an applied entry.
    - migrate() is idempotent — re-running against a migrated DB is a no-op.
    - No downgrade path: a DB newer than CURRENT_VERSION raises.
    - user_version is set AFTER the migration SQL succeeds; each migration
      uses CREATE ... IF NOT EXISTS so a crash between SQL and version bump
      is recoverable by simply re-running migrate().

Usage:
    from aether.task.migrations import migrate
    migrate(conn)   # applies pending migrations, returns final version
"""

from __future__ import annotations

import logging
import sqlite3
from typing import List, Tuple

from aether.task.schema import SCHEMA_SQL_V1

logger = logging.getLogger("Aether.task.migrations")

# Append-only. Target version → SQL script. Never modify an applied entry.
MIGRATIONS: List[Tuple[int, str]] = [
    (1, SCHEMA_SQL_V1),
]

CURRENT_VERSION = MIGRATIONS[-1][0]


class MigrationError(RuntimeError):
    """Raised when the database cannot be migrated safely."""


def user_version(conn: sqlite3.Connection) -> int:
    """Read the current schema version from PRAGMA user_version."""
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations. Returns the final schema version.

    Idempotent: an already-current database is untouched. Raises
    MigrationError if the DB version is newer than this build supports
    (no downgrade path) or if MIGRATIONS is malformed.
    """
    if not MIGRATIONS:
        raise MigrationError("MIGRATIONS is empty")
    targets = [t for t, _ in MIGRATIONS]
    if targets != sorted(targets) or len(set(targets)) != len(targets):
        raise MigrationError(f"MIGRATIONS targets not strictly ascending: {targets}")
    if targets[0] != 1:
        raise MigrationError(f"first migration must target version 1, got {targets[0]}")

    version = user_version(conn)
    if version > CURRENT_VERSION:
        raise MigrationError(
            f"database schema version {version} is newer than supported "
            f"{CURRENT_VERSION}; refusing to run (no downgrade path)"
        )

    for target, sql in MIGRATIONS:
        if target <= version:
            continue
        conn.executescript(sql)
        conn.execute(f"PRAGMA user_version = {target}")
        conn.commit()
        logger.info("tasks.db migrated to schema version %d", target)
        version = target

    return version
