"""Phase 3 tests — json_adapter export/import.

Rules under test:
- validation collects every structure/type problem and means zero writes
- file-level content_hash dedupe + per-item identical-content dedupe
- conflicts never silently overwritten (review | update | skip)
- one re-entrant transaction: items + review rows + import_batches row
  all-or-nothing; IMPORTED history for every actually-written item
- 4-digit years only, date-only stays date-only (no midnight), naive
  datetimes gain the item tz, foreign offsets preserved
"""

from __future__ import annotations

import json

import pytest

from aether.task import json_adapter
from aether.task.json_adapter import (
    ImportFormatError,
    ImportResult,
    content_hash,
    dumps,
    export_items,
    export_to_file,
    import_data,
    item_from_dict,
    load_and_validate,
)
from aether.task.models import (
    HistoryAction,
    ItemKind,
    ItemStatus,
    ReviewState,
    item_to_dict,
)
from aether.task.repository import SqliteScheduleRepository
from aether.task.service import ScheduleError, ScheduleService


@pytest.fixture
def repo(tmp_path):
    r = SqliteScheduleRepository(str(tmp_path / "tasks.db"))
    r.open()
    yield r
    r.close()


@pytest.fixture
def service(repo):
    return ScheduleService(repo)


def _task_dict(**kw):
    base = {
        "id": "item_aaaa00000001",
        "kind": "task",
        "title": "Pay rent",
        "description": "",
        "status": "pending",
        "internal_status": "confirmed",
        "due_date": "2026-11-05",
        "start_at": None,
        "end_at": None,
        "all_day": False,
        "tz": "Asia/Bangkok",
        "owner": None,
        "source": "manual",
        "created_at": 1.0,
        "updated_at": 1.0,
    }
    base.update(kw)
    return base


def _event_dict(**kw):
    base = {
        "id": "item_bbbb00000002",
        "kind": "event",
        "title": "Trip",
        "description": "",
        "status": "pending",
        "internal_status": "confirmed",
        "due_date": None,
        "start_at": "2026-10-20T09:00:00+07:00",
        "end_at": "2026-10-22T12:00:00+07:00",
        "all_day": False,
        "tz": "Asia/Bangkok",
        "owner": None,
        "source": "manual",
        "created_at": 1.0,
        "updated_at": 1.0,
    }
    base.update(kw)
    return base


def _payload(*items, version="1", source="aether-mark1"):
    return {
        "format_version": version,
        "source": source,
        "exported_at": "2026-10-19T10:00:00+07:00",
        "items": list(items),
    }


class TestExport:
    def test_payload_shape(self):
        payload = export_items([])
        assert payload["format_version"] == "1"
        assert payload["source"] == "aether-mark1"
        assert payload["items"] == []
        assert payload["exported_at"].endswith("+07:00")

    def test_export_then_import_same_db_is_identical_duplicate(self, service, repo):
        created = service.create(ItemKind.TASK, "ค่าเช่าบ้าน", due_date="2026-11-05")
        payload = export_items(service.list())
        raw = load_and_validate(payload)
        assert len(raw) == 1
        assert raw[0]["id"] == created.id

    def test_dumps_canonical_and_thai_not_escaped(self):
        payload = _payload(_task_dict(title="จ่ายค่าไฟ"))
        text = dumps(payload)
        assert "จ่ายค่าไฟ" in text
        assert "\\u0e01" not in text  # Thai not \u-escaped
        reordered = dict(reversed(list(payload.items())))
        assert dumps(reordered) == text

    def test_export_to_file_utf8(self, tmp_path, service):
        service.create(ItemKind.TASK, "ซื้อของขวัญ", due_date="2026-12-25")
        path = tmp_path / "nested" / "out.json"
        export_to_file(service.list(), str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["format_version"] == "1"
        assert data["items"][0]["title"] == "ซื้อของขวัญ"

    def test_content_hash_ignores_formatting(self):
        a = _payload(_task_dict())
        text = dumps(a).replace(",", ", ")  # same content, other whitespace
        assert text != dumps(a)
        b = json.loads(text)
        assert content_hash(a) == content_hash(b)

    def test_full_fidelity_roundtrip_second_db(self, service, repo, tmp_path):
        src = service.create(
            ItemKind.EVENT,
            "offsite",
            start_at="2026-10-20T09:00:00+09:00",
            end_at="2026-10-21T17:00:00+09:00",
            owner="alice",
            description="cross-machine roundtrip",
        )
        payload = export_items([src])

        repo2 = SqliteScheduleRepository(str(tmp_path / "tasks2.db"))
        repo2.open()
        try:
            service2 = ScheduleService(repo2)
            result = import_data(service2, repo2, payload)
            assert result.imported == 1
            got = service2.get(src.id)
            assert item_to_dict(got) == item_to_dict(src)  # foreign +09:00 intact
        finally:
            repo2.close()


class TestValidationCollectsErrors:
    def test_root_not_object(self):
        with pytest.raises(ImportFormatError, match="root"):
            load_and_validate([1, 2])

    def test_wrong_version(self):
        with pytest.raises(ImportFormatError) as exc:
            load_and_validate(_payload(version="2"))
        assert any("format_version" in e for e in exc.value.errors)

    def test_items_not_list(self):
        data = _payload()
        data["items"] = "x"
        with pytest.raises(ImportFormatError) as exc:
            load_and_validate(data)
        assert any(e.startswith("items:") for e in exc.value.errors)

    def test_multiple_errors_collected(self):
        bad = _payload(
            _task_dict(id=""),
            _task_dict(id="item_x2", kind="bogus"),
            _task_dict(id="item_x3", title="   "),
            _task_dict(id="item_x4", due_date="26-10-20"),
            _task_dict(id="item_x5", tz="Mars/Phobos"),
        )
        with pytest.raises(ImportFormatError) as exc:
            load_and_validate(bad)
        errs = exc.value.errors
        assert len(errs) >= 5
        joined = " ".join(errs)
        for needle in ("items[0].id", "items[1].kind", "items[2].title", "items[3].due_date", "items[4].tz"):
            assert needle in joined, needle

    def test_validation_failure_zero_writes(self, service, repo):
        data = _payload(_task_dict(), _task_dict(id="item_bad", due_date="26/10/2026"))
        with pytest.raises(ImportFormatError):
            import_data(service, repo, data)
        assert repo.count() == 0
        assert repo.list_reviews() == []

    def test_event_requires_start_at(self):
        with pytest.raises(ImportFormatError) as exc:
            load_and_validate(_payload(_event_dict(start_at=None, end_at=None)))
        assert any("start_at" in e for e in exc.value.errors)

    def test_event_rejects_due_date(self):
        with pytest.raises(ImportFormatError) as exc:
            load_and_validate(_payload(_event_dict(due_date="2026-11-05")))
        assert any("due_date" in e for e in exc.value.errors)

    def test_task_rejects_all_day(self):
        with pytest.raises(ImportFormatError) as exc:
            load_and_validate(_payload(_task_dict(all_day=True)))
        assert any("all_day" in e for e in exc.value.errors)

    def test_bare_date_requires_all_day(self):
        with pytest.raises(ImportFormatError) as exc:
            load_and_validate(_payload(_event_dict(start_at="2026-10-20", all_day=False)))
        assert any("all_day=true" in e for e in exc.value.errors)

    def test_all_day_rejects_timed_value(self):
        with pytest.raises(ImportFormatError) as exc:
            load_and_validate(_payload(_event_dict(all_day=True, start_at="2026-10-20T09:00:00+07:00")))
        assert any("all_day=true requires" in e for e in exc.value.errors)

    def test_two_digit_year_in_datetime_rejected(self):
        with pytest.raises(ImportFormatError) as exc:
            load_and_validate(_payload(_event_dict(start_at="26-10-20T09:00:00")))
        assert any("4-digit year" in e for e in exc.value.errors)

    def test_invalid_on_conflict_rejected(self, service, repo):
        with pytest.raises(ImportFormatError, match="on_conflict"):
            import_data(service, repo, _payload(), on_conflict="merge")

    def test_end_before_start_rejected(self):
        with pytest.raises(ImportFormatError, match="before start"):
            load_and_validate(_payload(_event_dict(
                start_at="2026-10-22T09:00:00+07:00",
                end_at="2026-10-20T09:00:00+07:00",
            )))

    # ── R1: chronology must compare instants, not raw strings ──────────

    def test_mixed_offset_end_before_start_rejected(self):
        # 14:00+09:00 == 05:00Z ; 08:00+07:00 == 01:00Z -> end is earlier.
        with pytest.raises(ImportFormatError, match="before start"):
            load_and_validate(_payload(_event_dict(
                start_at="2026-10-20T14:00:00+09:00",
                end_at="2026-10-20T08:00:00+07:00",
            )))

    def test_mixed_offset_same_instant_accepted(self):
        # 14:00+09:00 == 12:00+07:00 == 05:00Z ; string order said "end <
        # start" (12 < 14) and rejected — instants are equal.
        raw = load_and_validate(_payload(_event_dict(
            start_at="2026-10-20T14:00:00+09:00",
            end_at="2026-10-20T12:00:00+07:00",
        )))
        assert len(raw) == 1

    def test_lexicographic_false_reject_is_accepted(self):
        # 01:00+09:00 == 16:00Z(19th) ; 00:30+07:00 == 17:30Z(19th) -> end
        # is later in real time, but "00:30" < "01:00" as a string.
        raw = load_and_validate(_payload(_event_dict(
            start_at="2026-10-20T01:00:00+09:00",
            end_at="2026-10-20T00:30:00+07:00",
        )))
        assert len(raw) == 1

    def test_lexicographic_false_accept_is_rejected(self):
        # 02:00+07:00 == 19:00Z(19th) ; 03:00+09:00 == 18:00Z(19th) -> end
        # is earlier in real time, but "03:00" > "02:00" as a string.
        with pytest.raises(ImportFormatError, match="before start"):
            load_and_validate(_payload(_event_dict(
                start_at="2026-10-20T02:00:00+07:00",
                end_at="2026-10-20T03:00:00+09:00",
            )))

    def test_naive_end_before_aware_start_rejected(self):
        # Naive values are interpreted in the item tz before comparing.
        with pytest.raises(ImportFormatError, match="before start"):
            load_and_validate(_payload(_event_dict(
                start_at="2026-10-20T10:00:00+07:00",
                end_at="2026-10-20T09:00:00",
            )))

    def test_all_day_end_before_start_rejected(self):
        with pytest.raises(ImportFormatError, match="before start"):
            load_and_validate(_payload(_event_dict(
                all_day=True,
                start_at="2026-10-22",
                end_at="2026-10-20",
            )))

    def test_bad_status_rejected(self):
        with pytest.raises(ImportFormatError, match="status"):
            load_and_validate(_payload(_task_dict(status="archived")))

    def test_bad_internal_status_rejected(self):
        with pytest.raises(ImportFormatError, match="internal_status"):
            load_and_validate(_payload(_task_dict(internal_status="mystery")))

    def test_non_string_description_rejected(self):
        with pytest.raises(ImportFormatError, match="description"):
            load_and_validate(_payload(_task_dict(description=123)))


class TestItemFromDict:
    def test_naive_datetime_gains_item_tz(self):
        item = item_from_dict(_event_dict(start_at="2026-10-20T09:00:00", end_at="2026-10-20T10:00:00"))
        assert item.start_at == "2026-10-20T09:00:00+07:00"
        assert item.end_at == "2026-10-20T10:00:00+07:00"

    def test_foreign_offset_preserved(self):
        item = item_from_dict(_event_dict(start_at="2026-10-20T09:00:00+09:00"))
        assert item.start_at == "2026-10-20T09:00:00+09:00"

    def test_date_only_never_gains_time(self):
        item = item_from_dict(_event_dict(all_day=True, start_at="2026-10-20", end_at="2026-10-22"))
        assert item.start_at == "2026-10-20"
        assert item.end_at == "2026-10-22"

    def test_id_status_timestamps_preserved(self):
        raw = _task_dict(id="item_custom", status="completed", created_at=123.0, updated_at=456.0)
        item = item_from_dict(raw)
        assert item.id == "item_custom"
        assert item.status is ItemStatus.COMPLETED
        assert item.created_at == 123.0
        assert item.updated_at == 456.0

    def test_missing_timestamps_default(self):
        raw = _task_dict()
        del raw["created_at"]
        del raw["updated_at"]
        item = item_from_dict(raw)
        assert item.created_at > 0


class TestImportNewItems:
    def test_happy_path_counts_history_batch(self, service, repo):
        data = _payload(_task_dict(), _event_dict())
        result = import_data(service, repo, data)
        assert result.ok is True
        assert result.imported == 2
        assert result.conflicts == 0
        assert repo.count() == 2

        for iid in ("item_aaaa00000001", "item_bbbb00000002"):
            hist = service.history(iid)
            assert hist[0].action is HistoryAction.IMPORTED
            assert hist[0].before is None
            assert hist[0].after["id"] == iid

        batch = repo.find_batch_by_hash(content_hash(data))
        assert batch is not None
        assert batch.id == result.batch_id
        assert batch.item_count == 2
        assert batch.stats["imported"] == 2

    def test_batch_hash_dedupe_second_run_no_writes(self, service, repo):
        data = _payload(_task_dict())
        first = import_data(service, repo, data)
        assert first.imported == 1

        second = import_data(service, repo, data)
        assert second.already_imported is True
        assert second.batch_id == first.batch_id
        assert second.duplicates == 1
        assert repo.count() == 1
        assert len(service.history("item_aaaa00000001")) == 1  # only the first IMPORTED

    def test_same_content_different_formatting_same_hash(self, service, repo):
        data = _payload(_task_dict())
        assert import_data(service, repo, data).imported == 1
        reformatted = json.loads(json.dumps(data, indent=4))  # other whitespace
        assert json.dumps(reformatted, indent=4) != dumps(data)
        assert import_data(service, repo, reformatted).already_imported is True

    def test_mixed_offset_event_imports_and_preserves_offsets(self, service, repo):
        # R1 parity: the adapter must accept what the service accepts.
        result = import_data(service, repo, _payload(_event_dict(
            start_at="2026-10-20T14:00:00+09:00",
            end_at="2026-10-20T12:00:00+07:00",
        )))
        assert result.ok and result.imported == 1
        stored = repo.find_by_id("item_bbbb00000002")
        assert stored.start_at == "2026-10-20T14:00:00+09:00"
        assert stored.end_at == "2026-10-20T12:00:00+07:00"

    def test_naive_datetime_normalized_on_import(self, service, repo):
        raw = _event_dict(start_at="2026-10-20T09:00:00", end_at="2026-10-20T10:00:00")
        import_data(service, repo, _payload(raw))
        item = service.get("item_bbbb00000002")
        assert item.start_at == "2026-10-20T09:00:00+07:00"

    def test_history_survives_item_deletion(self, service, repo):
        data = _payload(_task_dict())
        import_data(service, repo, data)
        service.delete("item_aaaa00000001", actor="test")
        hist = service.history("item_aaaa00000001")
        assert any(h.action is HistoryAction.IMPORTED for h in hist)
        batch = repo.find_batch_by_hash(content_hash(data))
        assert batch.stats["imported"] == 1


class TestIdenticalDuplicates:
    def test_identical_item_without_matching_file_hash(self, service, repo):
        # File A: item X. File B: same X (identical) + new Y -> different hash.
        import_data(service, repo, _payload(_task_dict()))

        b = _payload(_task_dict(), _event_dict())
        result = import_data(service, repo, b)
        assert result.already_imported is False
        assert result.imported == 1  # Y
        assert result.duplicates == 1  # X identical
        assert result.conflicts == 0
        assert repo.count() == 2
        assert len(service.history("item_aaaa00000001")) == 1  # no second history


class TestConflictPolicies:
    @pytest.fixture
    def seeded(self, service):
        return service.create(ItemKind.TASK, "old title", due_date="2026-11-05", actor="seed")

    @staticmethod
    def _payload_with_edit(item):
        """Same id as ``item``, title changed — a real conflict, not a new id."""
        return _payload(_task_dict(id=item.id, title="new title", updated_at=item.updated_at + 1))

    def test_review_default_no_overwrite_parks(self, service, repo, seeded):
        data = self._payload_with_edit(seeded)
        result = import_data(service, repo, data)
        assert result.conflicts == 1
        assert result.parked == 1
        assert result.updated == 0
        assert result.conflict_ids == [seeded.id]

        stored = service.get(seeded.id)
        assert stored.title == "old title"  # untouched

        reviews = repo.list_reviews(ReviewState.PENDING)
        assert len(reviews) == 1
        assert reviews[0].item_id == seeded.id
        assert reviews[0].reason == "import conflict"
        assert reviews[0].payload["existing"]["title"] == "old title"
        assert reviews[0].payload["incoming"]["title"] == "new title"

        assert len(service.history(seeded.id)) == 1  # no extra history
        assert repo.find_batch_by_hash(content_hash(data)) is not None  # batch recorded

    def test_update_writes_with_before_after_history(self, service, repo, seeded):
        data = self._payload_with_edit(seeded)
        result = import_data(service, repo, data, on_conflict="update")
        assert result.updated == 1
        assert result.conflicts == 1
        assert result.parked == 0

        stored = service.get(seeded.id)
        assert stored.title == "new title"

        hist = service.history(seeded.id)
        assert hist[0].action is HistoryAction.IMPORTED
        assert hist[0].before["title"] == "old title"
        assert hist[0].after["title"] == "new title"

    def test_skip_counts_only(self, service, repo, seeded):
        data = self._payload_with_edit(seeded)
        result = import_data(service, repo, data, on_conflict="skip")
        assert result.skipped == 1
        assert result.conflicts == 1
        assert result.updated == 0
        assert result.parked == 0
        assert service.get(seeded.id).title == "old title"
        assert repo.list_reviews() == []
        assert len(service.history(seeded.id)) == 1

    def test_mixed_new_and_conflict_update(self, service, repo, seeded):
        data = self._payload_with_edit(seeded)
        data["items"].append(_event_dict())
        result = import_data(service, repo, data, on_conflict="update")
        assert result.imported == 1  # the new event
        assert result.updated == 1  # the edited task
        assert repo.count() == 2


class TestAtomicity:
    def test_domain_failure_rolls_back_everything(self, service, repo):
        # status "completed" passes structure validation but fails the
        # domain rule "events cannot be completed" inside _validate
        data = _payload(_task_dict(), _event_dict(id="item_bad00000001", status="completed"))
        with pytest.raises(ScheduleError):
            import_data(service, repo, data)
        assert repo.count() == 0  # the good item rolled back too
        assert repo.find_batch_by_hash(content_hash(data)) is None  # batch rolled back too
        assert repo.list_reviews() == []

    def test_retry_after_failure_imports_cleanly(self, service, repo):
        bad = _payload(_task_dict(), _event_dict(id="item_bad00000001", status="completed"))
        with pytest.raises(ScheduleError):
            import_data(service, repo, bad)

        good = _payload(_task_dict())
        assert import_data(service, repo, good).imported == 1
        assert repo.count() == 1


class TestResultShapeAndLoads:
    def test_import_result_as_dict_shape(self, service, repo):
        result = import_data(service, repo, _payload(_task_dict()))
        d = result.as_dict()
        assert set(d) == {
            "ok", "already_imported", "batch_id", "imported", "duplicates",
            "conflicts", "updated", "parked", "skipped", "conflict_ids", "message",
        }
        assert d["ok"] is True
        assert isinstance(result, ImportResult)

    def test_loads_parses_export_text(self, service):
        service.create(ItemKind.TASK, "x", due_date="2026-11-05")
        data = json_adapter.loads(dumps(export_items(service.list())))
        assert data["format_version"] == "1"
        assert len(data["items"]) == 1
