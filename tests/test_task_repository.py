"""Phase 1 tests — SqliteScheduleRepository CRUD + history + evidence + review.

Transaction semantics: mutation + history must commit or roll back together.
"""

from __future__ import annotations

import sqlite3

import pytest

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
    item_to_dict,
)
from aether.task.repository import SqliteScheduleRepository


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "tasks.db")


@pytest.fixture
def repo(db_path):
    r = SqliteScheduleRepository(db_path)
    r.open()
    yield r
    r.close()


def make_item(**kw) -> TaskItem:
    defaults = dict(kind=ItemKind.TASK, title="task-a", created_at=1.0, updated_at=1.0)
    defaults.update(kw)
    return TaskItem(**defaults)


class TestItemCrud:
    def test_save_and_find_roundtrip(self, repo):
        item = make_item(
            id="item_1",
            kind=ItemKind.EVENT,
            title="standup",
            description="daily sync",
            start_at="2026-10-20T09:30:00+07:00",
            end_at="2026-10-20T10:00:00+07:00",
            owner="alice",
            source="manual",
        )
        assert repo.save(item) is True
        got = repo.find_by_id("item_1")
        assert got == item

    def test_save_upserts(self, repo):
        repo.save(make_item(id="item_1", title="old"))
        repo.save(make_item(id="item_1", title="new", updated_at=2.0))
        assert repo.count() == 1
        assert repo.find_by_id("item_1").title == "new"

    def test_find_by_id_missing(self, repo):
        assert repo.find_by_id("nope") is None

    def test_find_all_filters(self, repo):
        repo.save(make_item(id="i1", kind=ItemKind.TASK))
        repo.save(make_item(id="i2", kind=ItemKind.EVENT, start_at="2026-10-20T10:00:00+07:00"))
        repo.save(make_item(id="i3", kind=ItemKind.TASK, status=ItemStatus.COMPLETED))
        assert [i.id for i in repo.find_all()] == ["i1", "i2", "i3"]
        assert [i.id for i in repo.find_all(kind=ItemKind.TASK)] == ["i1", "i3"]
        assert [i.id for i in repo.find_all(status=ItemStatus.COMPLETED)] == ["i3"]
        assert (
            [i.id for i in repo.find_all(kind=ItemKind.TASK, status=ItemStatus.PENDING)]
            == ["i1"]
        )

    def test_delete(self, repo):
        repo.save(make_item(id="item_1"))
        assert repo.delete("item_1") is True
        assert repo.delete("item_1") is False
        assert repo.find_by_id("item_1") is None

    def test_bool_and_enum_roundtrip(self, repo):
        item = make_item(
            id="item_1",
            all_day=True,
            kind=ItemKind.EVENT,
            start_at="2026-10-20",
            end_at="2026-10-21",
            internal_status=InternalStatus.NEEDS_CONFIRMATION,
            status=ItemStatus.CANCELLED,
        )
        # all_day on event with date-only values passes schema CHECKs.
        repo.save(item)
        got = repo.find_by_id("item_1")
        assert got.all_day is True
        assert got.internal_status is InternalStatus.NEEDS_CONFIRMATION
        assert got.status is ItemStatus.CANCELLED


class TestEvidence:
    def test_add_and_get(self, repo):
        repo.save(make_item(id="item_1"))
        ev = [
            Evidence(id="e1", item_id="item_1", source="chat", source_ref="line_42",
                     excerpt="buy milk", confidence=0.9, created_at=1.0),
            Evidence(id="e2", item_id="item_1", source="chat", source_ref="line_43",
                     excerpt="tomorrow", confidence=0.5, created_at=2.0),
        ]
        assert repo.add_evidence(ev) == 2
        got = repo.get_evidence("item_1")
        assert [e.id for e in got] == ["e1", "e2"]
        assert got[0].confidence == 0.9

    def test_add_empty_is_noop(self, repo):
        assert repo.add_evidence([]) == 0

    def test_cascades_on_item_delete(self, repo):
        repo.save(make_item(id="item_1"))
        repo.add_evidence([Evidence(item_id="item_1")])
        repo.delete("item_1")
        assert repo.get_evidence("item_1") == []

    def test_confidence_out_of_range_rejected(self, repo):
        repo.save(make_item(id="item_1"))
        with pytest.raises(sqlite3.IntegrityError):
            repo.add_evidence([Evidence(item_id="item_1", confidence=1.5)])


class TestHistory:
    def test_append_and_get_newest_first(self, repo):
        repo.save(make_item(id="item_1"))
        for ts, action in [(1.0, HistoryAction.CREATED), (2.0, HistoryAction.UPDATED)]:
            repo.append_history(
                HistoryEntry(
                    id=f"h{ts}", item_id="item_1", action=action,
                    before={"x": 1} if ts > 1 else None,
                    after={"x": 2}, changed_fields=["x"], actor="tester",
                    created_at=ts,
                )
            )
        got = repo.get_history("item_1")
        assert [h.action for h in got] == [HistoryAction.UPDATED, HistoryAction.CREATED]
        assert got[0].before == {"x": 1}
        assert got[0].after == {"x": 2}
        assert got[0].changed_fields == ["x"]
        assert got[0].actor == "tester"

    def test_history_survives_item_delete(self, repo):
        repo.save(make_item(id="item_1"))
        repo.append_history(HistoryEntry(item_id="item_1", action=HistoryAction.CREATED))
        repo.delete("item_1")
        assert len(repo.get_history("item_1")) == 1

    def test_history_limit(self, repo):
        repo.save(make_item(id="item_1"))
        for i in range(5):
            repo.append_history(
                HistoryEntry(id=f"h{i}", item_id="item_1", created_at=float(i))
            )
        assert len(repo.get_history("item_1", limit=3)) == 3

    def test_utf8_history(self, repo):
        repo.save(make_item(id="item_1"))
        repo.append_history(
            HistoryEntry(item_id="item_1", after={"title": "ซื้อนม"})
        )
        assert repo.get_history("item_1")[0].after == {"title": "ซื้อนม"}


class TestReviewQueue:
    def test_enqueue_list_resolve(self, repo):
        repo.save(make_item(id="item_1"))
        repo.enqueue_review(
            ReviewEntry(id="r1", item_id="item_1", reason="ambiguous_date",
                        payload={"candidates": ["2026-10-20", "2026-11-20"]},
                        confidence=0.4)
        )
        pending = repo.list_reviews(state=ReviewState.PENDING)
        assert len(pending) == 1
        assert pending[0].payload["candidates"] == ["2026-10-20", "2026-11-20"]

        assert repo.resolve_review("r1", ReviewState.CONFIRMED, 99.0) is True
        assert repo.list_reviews(state=ReviewState.PENDING) == []
        resolved = repo.list_reviews(state=ReviewState.CONFIRMED)
        assert len(resolved) == 1 and resolved[0].resolved_at == 99.0

    def test_resolve_only_pending(self, repo):
        repo.save(make_item(id="item_1"))
        repo.enqueue_review(ReviewEntry(id="r1", item_id="item_1", reason="x"))
        assert repo.resolve_review("r1", ReviewState.REJECTED, 5.0) is True
        assert repo.resolve_review("r1", ReviewState.CONFIRMED, 6.0) is False
        assert repo.list_reviews(state=ReviewState.PENDING) == []

    def test_one_pending_review_per_item(self, repo):
        repo.save(make_item(id="item_1"))
        repo.enqueue_review(ReviewEntry(id="r1", item_id="item_1", reason="x"))
        with pytest.raises(sqlite3.IntegrityError):
            repo.enqueue_review(ReviewEntry(id="r2", item_id="item_1", reason="y"))

    def test_review_cascades_on_delete(self, repo):
        repo.save(make_item(id="item_1"))
        repo.enqueue_review(ReviewEntry(id="r1", item_id="item_1", reason="x"))
        repo.delete("item_1")
        assert repo.list_reviews(state=None) == []


class TestImportBatches:
    def test_record_and_find_by_hash(self, repo):
        b = ImportBatch(id="b1", source="json", content_hash="h" * 64,
                        item_count=3, stats={"created": 3})
        assert repo.record_batch(b) is True
        got = repo.find_batch_by_hash("h" * 64)
        assert got == b

    def test_duplicate_hash_rejected(self, repo):
        repo.record_batch(ImportBatch(content_hash="dup"))
        with pytest.raises(sqlite3.IntegrityError):
            repo.record_batch(ImportBatch(content_hash="dup"))

    def test_find_missing_hash(self, repo):
        assert repo.find_batch_by_hash("missing") is None


class TestTransactions:
    def test_transaction_commits(self, repo):
        with repo.transaction():
            repo.save(make_item(id="item_1"))
            repo.append_history(HistoryEntry(item_id="item_1"))
        assert repo.find_by_id("item_1") is not None
        assert len(repo.get_history("item_1")) == 1

    def test_transaction_rolls_back(self, repo):
        with pytest.raises(RuntimeError):
            with repo.transaction():
                repo.save(make_item(id="item_1"))
                repo.append_history(HistoryEntry(item_id="item_1"))
                raise RuntimeError("boom")
        assert repo.find_by_id("item_1") is None
        assert repo.get_history("item_1") == []

    def test_transaction_is_reentrant(self, repo):
        with repo.transaction():
            repo.save(make_item(id="item_1"))
            with repo.transaction():
                repo.append_history(HistoryEntry(item_id="item_1"))
        assert repo.find_by_id("item_1") is not None

    def test_cascade_delete_inside_transaction(self, repo):
        with repo.transaction():
            repo.save(make_item(id="item_1"))
            repo.add_evidence([Evidence(item_id="item_1")])
            repo.delete("item_1")
        assert repo.find_by_id("item_1") is None
        assert repo.get_evidence("item_1") == []
