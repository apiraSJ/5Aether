"""Aether Mark 1 — task & calendar schedule domain.

Public surface:
    ScheduleService      — validated, audited CRUD (use this, not the repo)
    SqliteScheduleRepository — SQLite storage for data/tasks.db
    TaskItem / Evidence / HistoryEntry / ReviewEntry / ImportBatch
    ItemKind / ItemStatus / InternalStatus / HistoryAction / ReviewState

Phase 1 ships models + schema + migrations + repository + service only.
Plugin/command wiring, calendar queries, JSON import/export, the temporal
engine, chat extraction, review commands, and the web backend arrive in
later phases.
"""

from aether.task.models import (
    DEFAULT_TZ,
    TZ_OFFSETS,
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
    is_date_only,
    item_to_dict,
    normalize_datetime,
    tzinfo_for,
)
from aether.task.migrations import CURRENT_VERSION, MigrationError, migrate, user_version
from aether.task.repository import SqliteScheduleRepository
from aether.task.service import (
    ScheduleConflictError,
    ScheduleError,
    ScheduleNotFoundError,
    ScheduleService,
    ScheduleValidationError,
)

__all__ = [
    "DEFAULT_TZ",
    "TZ_OFFSETS",
    "Evidence",
    "HistoryAction",
    "HistoryEntry",
    "ImportBatch",
    "InternalStatus",
    "ItemKind",
    "ItemStatus",
    "ReviewEntry",
    "ReviewState",
    "TaskItem",
    "is_date_only",
    "item_to_dict",
    "normalize_datetime",
    "tzinfo_for",
    "CURRENT_VERSION",
    "MigrationError",
    "migrate",
    "user_version",
    "SqliteScheduleRepository",
    "ScheduleConflictError",
    "ScheduleError",
    "ScheduleNotFoundError",
    "ScheduleService",
    "ScheduleValidationError",
]
