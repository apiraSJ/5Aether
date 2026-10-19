"""Phase 1 tests — Mark 1 task/calendar models (aether.task.models)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from aether.task.models import (
    DEFAULT_TZ,
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


class TestTaskItem:
    def test_defaults(self):
        item = TaskItem(title="write report")
        assert item.id.startswith("item_")
        assert item.kind is ItemKind.TASK
        assert item.status is ItemStatus.PENDING
        assert item.internal_status is InternalStatus.CONFIRMED
        assert item.due_date is None
        assert item.start_at is None
        assert item.end_at is None
        assert item.all_day is False
        assert item.tz == DEFAULT_TZ
        assert item.source == "manual"
        assert item.created_at == pytest.approx(item.updated_at, abs=0.01)

    def test_frozen(self):
        item = TaskItem(title="x")
        with pytest.raises(AttributeError):
            item.title = "y"  # type: ignore[misc]

    def test_unique_ids(self):
        assert TaskItem(title="a").id != TaskItem(title="b").id


class TestEnums:
    def test_values(self):
        assert ItemKind.TASK.value == "task"
        assert ItemKind.EVENT.value == "event"
        assert ItemStatus.PENDING.value == "pending"
        assert ItemStatus.COMPLETED.value == "completed"
        assert ItemStatus.CANCELLED.value == "cancelled"
        assert InternalStatus.CONFIRMED.value == "confirmed"
        assert (
            InternalStatus.NEEDS_CONFIRMATION.value == "needs_confirmation"
        )
        assert HistoryAction.IMPORTED.value == "imported"
        assert ReviewState.PENDING.value == "pending"


class TestTimezoneHelpers:
    def test_tzinfo_for_bangkok_is_utc7(self):
        tz = tzinfo_for("Asia/Bangkok")
        assert tz.utcoffset(None).total_seconds() == 7 * 3600

    def test_tzinfo_for_unknown_raises(self):
        with pytest.raises(ValueError, match="unsupported timezone"):
            tzinfo_for("Mars/Olympus")

    def test_normalize_attaches_tz_to_naive(self):
        out = normalize_datetime("2026-10-20T09:30", "Asia/Bangkok")
        assert out == "2026-10-20T09:30:00+07:00"

    def test_normalize_keeps_aware(self):
        out = normalize_datetime("2026-10-20T09:30:00+07:00", "Asia/Bangkok")
        assert out == "2026-10-20T09:30:00+07:00"

    def test_normalize_invalid_raises(self):
        with pytest.raises(ValueError):
            normalize_datetime("not-a-date", "Asia/Bangkok")

    def test_is_date_only(self):
        assert is_date_only("2026-10-20")
        assert not is_date_only("2026-10-20T10:00")
        assert not is_date_only("2026-123")
        assert not is_date_only("garbage")


class TestItemToDict:
    def test_roundtrip_values(self):
        item = TaskItem(
            id="item_x",
            kind=ItemKind.EVENT,
            title="meeting",
            due_date=None,
            start_at="2026-10-20T09:30:00+07:00",
            all_day=False,
        )
        d = item_to_dict(item)
        assert d["kind"] == "event"
        assert d["status"] == "pending"
        assert d["internal_status"] == "confirmed"
        assert d["start_at"] == "2026-10-20T09:30:00+07:00"
        assert d["all_day"] is False
        assert set(d) == {
            "id",
            "kind",
            "title",
            "description",
            "status",
            "internal_status",
            "due_date",
            "start_at",
            "end_at",
            "all_day",
            "tz",
            "owner",
            "source",
            "created_at",
            "updated_at",
        }


class TestSupportingModels:
    def test_evidence_defaults(self):
        e = Evidence(item_id="item_1")
        assert e.id.startswith("evid_")
        assert e.confidence == 1.0

    def test_history_defaults(self):
        h = HistoryEntry(item_id="item_1")
        assert h.action is HistoryAction.CREATED
        assert h.before is None and h.after is None
        assert h.changed_fields == []
        assert h.actor == "system"

    def test_review_defaults(self):
        r = ReviewEntry(item_id="item_1", reason="ambiguous")
        assert r.state is ReviewState.PENDING
        assert r.resolved_at is None

    def test_import_batch_defaults(self):
        b = ImportBatch(content_hash="abc")
        assert b.format_version == "1"
        assert b.item_count == 0
