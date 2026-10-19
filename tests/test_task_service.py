"""Phase 1 tests — ScheduleService validation, lifecycle, conflict, history.

Phase 1 acceptance lives here:
    - per-kind validation (due_date vs start_at/end_at separation)
    - mutation + history atomic in one transaction
    - optimistic concurrency (expected_updated_at)
    - restart persistence
"""

from __future__ import annotations

import time

import pytest

from aether.task.migrations import user_version
from aether.task.models import (
    HistoryAction,
    InternalStatus,
    ItemKind,
    ItemStatus,
)
from aether.task.repository import SqliteScheduleRepository
from aether.task.service import (
    ScheduleConflictError,
    ScheduleNotFoundError,
    ScheduleService,
    ScheduleValidationError,
)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "tasks.db")


@pytest.fixture
def repo(db_path):
    r = SqliteScheduleRepository(db_path)
    r.open()
    yield r
    r.close()


@pytest.fixture
def service(repo):
    return ScheduleService(repo)


class TestCreateValidation:
    def test_task_minimal(self, service):
        item = service.create(ItemKind.TASK, "buy milk")
        assert item.kind is ItemKind.TASK
        assert item.status is ItemStatus.PENDING
        assert item.internal_status is InternalStatus.CONFIRMED
        assert item.tz == "Asia/Bangkok"

    def test_task_with_due_date(self, service):
        item = service.create(ItemKind.TASK, "report", due_date="2026-10-20")
        assert item.due_date == "2026-10-20"

    def test_task_bad_due_date_rejected(self, service):
        with pytest.raises(ScheduleValidationError, match="due_date"):
            service.create(ItemKind.TASK, "x", due_date="2026-10-20T10:00")

    def test_task_with_all_day_rejected(self, service):
        with pytest.raises(ScheduleValidationError, match="all_day"):
            service.create(ItemKind.TASK, "x", all_day=True)

    def test_event_requires_start(self, service):
        with pytest.raises(ScheduleValidationError, match="start_at"):
            service.create(ItemKind.EVENT, "meeting")

    def test_event_rejects_due_date(self, service):
        with pytest.raises(ScheduleValidationError, match="due_date"):
            service.create(
                ItemKind.EVENT, "meeting",
                start_at="2026-10-20T10:00:00+07:00",
                due_date="2026-10-20",
            )

    def test_event_timed_ok(self, service):
        item = service.create(
            ItemKind.EVENT, "meeting",
            start_at="2026-10-20T10:00:00+07:00",
            end_at="2026-10-20T11:00:00+07:00",
        )
        assert item.start_at == "2026-10-20T10:00:00+07:00"

    def test_event_all_day_stays_date_only(self, service):
        """All-day values must never be inflated to midnight datetimes."""
        item = service.create(
            ItemKind.EVENT, "loy krathong", all_day=True,
            start_at="2026-11-05", end_at="2026-11-05",
        )
        assert item.start_at == "2026-11-05"
        assert "T" not in item.start_at
        assert item.end_at == "2026-11-05"

    def test_event_all_day_rejects_datetime(self, service):
        with pytest.raises(ScheduleValidationError, match="all_day"):
            service.create(
                ItemKind.EVENT, "x", all_day=True,
                start_at="2026-11-05T00:00:00+07:00",
            )

    def test_event_end_before_start_rejected(self, service):
        with pytest.raises(ScheduleValidationError, match="before start_at"):
            service.create(
                ItemKind.EVENT, "x",
                start_at="2026-10-20T11:00:00+07:00",
                end_at="2026-10-20T10:00:00+07:00",
            )

    def test_all_day_end_before_start_rejected(self, service):
        with pytest.raises(ScheduleValidationError, match="before start_at"):
            service.create(
                ItemKind.EVENT, "x", all_day=True,
                start_at="2026-11-06", end_at="2026-11-05",
            )

    # R1: service compares instants (mixed offsets), matching json_adapter.
    def test_mixed_offset_same_instant_accepted(self, service):
        item = service.create(
            ItemKind.EVENT, "sync",
            start_at="2026-10-20T14:00:00+09:00",
            end_at="2026-10-20T12:00:00+07:00",
        )
        assert item.start_at == "2026-10-20T14:00:00+09:00"
        assert item.end_at == "2026-10-20T12:00:00+07:00"

    def test_mixed_offset_end_before_start_rejected(self, service):
        with pytest.raises(ScheduleValidationError, match="before start_at"):
            service.create(
                ItemKind.EVENT, "x",
                start_at="2026-10-20T14:00:00+09:00",
                end_at="2026-10-20T08:00:00+07:00",
            )

    def test_lexicographic_false_reject_is_accepted(self, service):
        item = service.create(
            ItemKind.EVENT, "x",
            start_at="2026-10-20T01:00:00+09:00",
            end_at="2026-10-20T00:30:00+07:00",
        )
        assert item.end_at == "2026-10-20T00:30:00+07:00"

    def test_empty_title_rejected(self, service):
        with pytest.raises(ScheduleValidationError, match="title"):
            service.create(ItemKind.TASK, "   ")

    def test_unknown_timezone_rejected(self, service):
        with pytest.raises(ScheduleValidationError, match="timezone"):
            service.create(ItemKind.TASK, "x", tz="Mars/Olympus")

    def test_naive_datetime_gets_tz_offset(self, service):
        item = service.create(
            ItemKind.EVENT, "sync", start_at="2026-10-20T14:30"
        )
        assert item.start_at == "2026-10-20T14:30:00+07:00"

    def test_create_writes_history(self, service):
        item = service.create(ItemKind.TASK, "audited", actor="alice")
        hist = service.history(item.id)
        assert len(hist) == 1
        assert hist[0].action is HistoryAction.CREATED
        assert hist[0].actor == "alice"
        assert hist[0].after["title"] == "audited"
        assert hist[0].before is None


class TestRead:
    def test_get_missing_raises(self, service):
        with pytest.raises(ScheduleNotFoundError):
            service.get("item_missing")

    def test_list_filters(self, service):
        service.create(ItemKind.TASK, "a")
        service.create(ItemKind.EVENT, "b", start_at="2026-10-20T10:00:00+07:00")
        assert len(service.list()) == 2
        assert len(service.list(kind=ItemKind.TASK)) == 1
        assert len(service.list(kind=ItemKind.EVENT)) == 1


class TestUpdate:
    def test_update_fields(self, service):
        item = service.create(ItemKind.TASK, "old", due_date="2026-10-20")
        updated = service.update(item.id, title="new", owner="bob")
        assert updated.title == "new"
        assert updated.owner == "bob"
        assert updated.due_date == "2026-10-20"
        assert updated.updated_at > item.updated_at

    def test_update_writes_history_with_changes(self, service):
        item = service.create(ItemKind.TASK, "old")
        service.update(item.id, title="new", owner="bob")
        hist = service.history(item.id)
        assert hist[0].action is HistoryAction.UPDATED
        assert hist[0].changed_fields == ["owner", "title"]
        assert hist[0].before["title"] == "old"
        assert hist[0].after["title"] == "new"

    def test_update_immutable_fields_rejected(self, service):
        item = service.create(ItemKind.TASK, "x")
        with pytest.raises(ScheduleValidationError, match="immutable|unknown"):
            service.update(item.id, id="item_evil")

    def test_update_no_changes_rejected(self, service):
        item = service.create(ItemKind.TASK, "x")
        with pytest.raises(ScheduleValidationError, match="no changes"):
            service.update(item.id)

    def test_update_unknown_field_rejected(self, service):
        item = service.create(ItemKind.TASK, "x")
        with pytest.raises(ScheduleValidationError, match="immutable|unknown"):
            service.update(item.id, not_a_field="x")

    def test_update_string_status_coerced(self, service):
        item = service.create(ItemKind.TASK, "x")
        updated = service.update(item.id, status="completed")
        assert updated.status is ItemStatus.COMPLETED

    def test_update_same_value_not_in_changed_fields(self, service):
        item = service.create(ItemKind.TASK, "x", due_date="2026-10-20")
        updated = service.update(item.id, due_date="2026-10-20")
        assert "due_date" not in [
            h.changed_fields for h in service.history(item.id) if h.action is HistoryAction.UPDATED
        ][0]

    def test_update_missing_raises(self, service):
        with pytest.raises(ScheduleNotFoundError):
            service.update("item_missing", title="x")


class TestConflict:
    def test_stale_updated_at_conflicts(self, service):
        item = service.create(ItemKind.TASK, "x")
        with pytest.raises(ScheduleConflictError):
            service.update(item.id, title="y", expected_updated_at=0.0)

    def test_fresh_updated_at_passes(self, service):
        item = service.create(ItemKind.TASK, "x")
        updated = service.update(item.id, title="y", expected_updated_at=item.updated_at)
        assert updated.title == "y"


class TestLifecycle:
    def test_complete_task(self, service):
        item = service.create(ItemKind.TASK, "x")
        completed = service.complete(item.id)
        assert completed.status is ItemStatus.COMPLETED
        assert len(service.history(item.id)) == 2
        assert service.history(item.id)[0].action is HistoryAction.COMPLETED

    def test_complete_event_rejected(self, service):
        item = service.create(ItemKind.EVENT, "x", start_at="2026-10-20T10:00:00+07:00")
        with pytest.raises(ScheduleValidationError, match="only tasks can be completed"):
            service.complete(item.id)

    def test_complete_twice_rejected(self, service):
        item = service.create(ItemKind.TASK, "x")
        service.complete(item.id)
        with pytest.raises(ScheduleValidationError, match="cannot complete item"):
            service.complete(item.id)

    def test_cancel_task_and_event(self, service):
        task = service.create(ItemKind.TASK, "x")
        event = service.create(ItemKind.EVENT, "y", start_at="2026-10-20T10:00:00+07:00")
        service.cancel(task.id)
        service.cancel(event.id)
        assert service.get(task.id).status is ItemStatus.CANCELLED
        assert service.get(event.id).status is ItemStatus.CANCELLED

    def test_cancel_completed_rejected(self, service):
        item = service.create(ItemKind.TASK, "x")
        service.complete(item.id)
        with pytest.raises(ScheduleValidationError, match="cannot cancel item"):
            service.cancel(item.id)

    def test_terminal_status_never_reverts_via_update(self, service):
        item = service.create(ItemKind.TASK, "x")
        service.complete(item.id)
        with pytest.raises(ScheduleValidationError, match="terminal"):
            service.update(item.id, status="pending")


class TestDelete:
    def test_delete_writes_history_and_cascades(self, service, repo):
        item = service.create(ItemKind.TASK, "x")
        service.attach_evidence(item.id, source="chat", source_ref="ref", excerpt="e")
        service.delete(item.id)
        assert repo.find_by_id(item.id) is None
        assert repo.get_evidence(item.id) == []
        hist = service.history(item.id)
        assert len(hist) == 2
        assert hist[0].action is HistoryAction.DELETED

    def test_delete_missing_raises(self, service):
        with pytest.raises(ScheduleNotFoundError):
            service.delete("item_missing")


class TestEvidence:
    def test_attach(self, service, repo):
        item = service.create(ItemKind.TASK, "with source")
        ev = service.attach_evidence(
            item.id, source="chat", source_ref="line_42",
            excerpt="buy milk tomorrow", confidence=0.8,
        )
        got = repo.get_evidence(item.id)
        assert len(got) == 1
        assert got[0].excerpt == "buy milk tomorrow"
        assert got[0].confidence == 0.8
        assert ev.item_id == item.id

    def test_attach_missing_item_raises(self, service):
        with pytest.raises(ScheduleNotFoundError):
            service.attach_evidence("item_missing", source="chat", source_ref="line_1")


class TestTransactionAtomicity:
    def test_create_is_atomic(self, service, repo):
        item = service.create(ItemKind.TASK, "atomic")
        assert repo.find_by_id(item.id) is not None
        assert len(repo.get_history(item.id)) == 1

    def test_update_history_failure_rolls_back_item(self, service, repo, monkeypatch):
        item = service.create(ItemKind.TASK, "x")
        original = repo.append_history

        def boom(entry):
            raise RuntimeError("history write failed")

        monkeypatch.setattr(repo, "append_history", boom)
        with pytest.raises(RuntimeError, match="history write failed"):
            service.update(item.id, title="should not persist")
        monkeypatch.setattr(repo, "append_history", original)
        assert service.get(item.id).title == "x"
        assert len(service.history(item.id)) == 1

    def test_complete_history_failure_rolls_back_status(self, service, repo, monkeypatch):
        item = service.create(ItemKind.TASK, "x")

        def boom(entry):
            raise RuntimeError("nope")

        monkeypatch.setattr(repo, "append_history", boom)
        with pytest.raises(RuntimeError):
            service.complete(item.id)
        assert service.get(item.id).status is ItemStatus.PENDING


class TestRestartPersistence:
    def test_data_survives_reopen(self, db_path):
        r1 = SqliteScheduleRepository(db_path)
        r1.open()
        s1 = ScheduleService(r1)
        item = s1.create(
            ItemKind.EVENT, "persisted", all_day=True,
            start_at="2026-11-05", owner="alice",
        )
        s1.attach_evidence(item.id, source="chat", source_ref="line_9")
        r1.close()

        r2 = SqliteScheduleRepository(db_path)
        r2.open()
        s2 = ScheduleService(r2)
        got = s2.get(item.id)
        assert got.title == "persisted"
        assert got.all_day is True
        assert got.start_at == "2026-11-05"
        assert got.owner == "alice"
        assert len(s2.history(item.id)) == 1
        assert len(r2.get_evidence(item.id)) == 1
        assert user_version(r2._conn) == 1
        r2.close()

    def test_wal_files_created(self, db_path):
        from pathlib import Path

        r = SqliteScheduleRepository(db_path)
        r.open()
        assert Path(db_path).exists()
        assert Path(db_path + "-wal").exists()
        mode = r._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        r.close()


class TestRepositoryGuards:
    def test_closed_repo_raises(self, db_path):
        from aether.task.repository import SqliteScheduleRepository as R

        r = R(db_path)
        with pytest.raises(RuntimeError, match="not open"):
            r.save(make_task())

    def test_double_open_is_noop(self, db_path):
        r = SqliteScheduleRepository(db_path)
        r.open()
        try:
            r.open()
            assert r.is_open
        finally:
            r.close()


def make_task():
    from aether.task.models import TaskItem

    return TaskItem(title="x")