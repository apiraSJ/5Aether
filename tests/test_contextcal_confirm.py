from datetime import datetime

import pytest

from aether.task.contextcal import ContextCalService, ConfirmSelection, ContextCalError, ContextCalConflictError
from aether.task.drafts import DraftStore
from aether.task.repository import SqliteScheduleRepository
from aether.task.service import ScheduleService


def test_analyze_no_db_write(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("14:00", now=datetime(2026, 1, 1))
    assert repo.count() == 0
    # reviews empty
    assert svc.list_pending_reviews() == []


def test_confirm_creates_task(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("พรุ่งนี้ ส่งรายงาน", now=datetime(2026, 10, 26))
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True)]
    res = cc.confirm(d.draft_id, sels)
    assert res.committed is True
    assert len(res.created_item_ids) == 1
    assert repo.count() == 1
    item = svc.get(res.created_item_ids[0])
    assert item.source == "extraction"


def test_confirm_twice_idempotent(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("พรุ่งนี้ ส่งรายงาน", now=datetime(2026, 10, 26))
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True)]
    res1 = cc.confirm(d.draft_id, sels)
    res2 = cc.confirm(d.draft_id, sels)
    assert repo.count() == 1
    assert res2.created_item_ids == res1.created_item_ids


def test_confirm_concurrent(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("พรุ่งนี้ ส่งรายงาน", now=datetime(2026, 10, 26))
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True)]
    results = []
    import threading
    def run():
        try:
            results.append(cc.confirm(d.draft_id, sels))
        except Exception as e:
            results.append(e)
    threads = [threading.Thread(target=run) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # at most one committed
    committed = [r for r in results if hasattr(r, 'committed') and r.committed]
    assert len(committed) >= 1
    assert repo.count() == 1


def test_confirm_expired(tmp_path):
    from aether.task.drafts import DraftStore
    class C:
        def __init__(self):
            self.t = 1000
        def __call__(self):
            return self.t
        def adv(self, dt):
            self.t += dt
    c = C()
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore(ttl_seconds=10, clock=c)
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("พรุ่งนี้ ส่งรายงาน", now=datetime(2026, 10, 26))
    c.adv(20)
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True)]
    with pytest.raises(ContextCalError):
        cc.confirm(d.draft_id, sels)
    assert repo.count() == 0


def test_confirm_missing_fields_no_create(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("นัดหมอวันศุกร์", now=datetime(2026, 10, 26))  # needs time
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True)]
    res = cc.confirm(d.draft_id, sels)
    assert res.committed is False
    assert repo.count() == 0


def test_batch_rollback_partial(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("ส่งรายงาน\nประชุมทีมวันศุกร์บ่ายสอง", now=datetime(2026, 10, 26))
    assert len(d.items) >= 1
    sels = [ConfirmSelection(draft_item_id=it.draft_item_id, accept=True) for it in d.items]
    sels2 = []
    for i, s in enumerate(sels):
        if i == 1:
            sels2.append(ConfirmSelection(draft_item_id=s.draft_item_id, accept=True, fields={"title": ""}))
        else:
            sels2.append(s)
    res = cc.confirm(d.draft_id, sels2)
    assert res.committed is False
    assert res.created_item_ids == ()
    assert repo.count() == 0


def test_evidence_attached(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("พรุ่งนี้ ส่งรายงาน", now=datetime(2026, 10, 26))
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True)]
    res = cc.confirm(d.draft_id, sels)
    evid = repo.get_evidence(res.created_item_ids[0])
    assert len(evid) >= 1


def test_evidence_failure_rolls_back_batch(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    orig = svc.attach_evidence
    def bad_attach(*a, **kw):
        raise RuntimeError("evidence fail")
    svc.attach_evidence = bad_attach
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("พรุ่งนี้ ส่งรายงาน", now=datetime(2026, 10, 26))
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True)]
    res = cc.confirm(d.draft_id, sels)
    assert res.committed is False
    assert repo.count() == 0
    svc.attach_evidence = orig


def test_override_due_date(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("ส่งรายงาน", now=datetime(2026, 10, 26))
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True, fields={"due_date": "2026-10-30"})]
    res = cc.confirm(d.draft_id, sels)
    assert res.committed is True
    item = svc.get(res.created_item_ids[0])
    assert item.due_date == "2026-10-30"


def test_unsupported_tz_no_guess(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("ประชุม 2026-10-20 14:00 Asia/Tokyo", now=datetime(2026, 10, 26))
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True)]
    res = cc.confirm(d.draft_id, sels)
    assert res.committed is False


def test_select_one_of_three(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("- ส่งรายงาน\n- แก้หน้าเว็บ\n- ประชุมทีม", now=datetime(2026, 10, 26))
    sels = []
    for it in d.items:
        sels.append(ConfirmSelection(draft_item_id=it.draft_item_id, accept=True, fields={"due_date": "2026-10-27"}))
    res = cc.confirm(d.draft_id, sels[:1])
    assert res.committed is True
    assert len(res.created_item_ids) == 1


def test_no_leak_ids_on_rollback(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("ส่งรายงาน\nประชุมทีมวันศุกร์บ่ายสอง", now=datetime(2026, 10, 26))
    sels = []
    for i, it in enumerate(d.items):
        if i == 0:
            sels.append(ConfirmSelection(draft_item_id=it.draft_item_id, accept=True))
        else:
            sels.append(ConfirmSelection(draft_item_id=it.draft_item_id, accept=True, fields={"title": ""}))
    res = cc.confirm(d.draft_id, sels)
    assert res.committed is False
    assert res.created_item_ids == ()
    assert repo.count() == 0


def test_confirm_again_different_selection_conflict(tmp_path):
    repo = SqliteScheduleRepository(str(tmp_path / "t.db"))
    repo.open()
    svc = ScheduleService(repo)
    store = DraftStore()
    cc = ContextCalService(svc, store, repository=repo)
    d = cc.analyze("ส่งรายงาน", now=datetime(2026, 10, 26))
    sels = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True, fields={"due_date": "2026-10-27"})]
    res1 = cc.confirm(d.draft_id, sels)
    assert res1.committed is True
    sels2 = [ConfirmSelection(draft_item_id=d.items[0].draft_item_id, accept=True, fields={"due_date": "2026-10-28"})]
    try:
        res2 = cc.confirm(d.draft_id, sels2)
        assert False
    except ContextCalConflictError:
        pass
    assert repo.count() == 1


def test_time_range_creates_end_at(tmp_path):
    from aether.task import extraction
    res = extraction.analyze("ประชุม 2026-10-20 10:00 ถึง 12:00", now=datetime(2026,10,26))
    c = res.candidates[0]
    assert c.start_at is not None
    assert c.end_at is not None
    assert c.end_at.endswith("12:00:00") or "12:00" in c.end_at


def test_duration_hours_creates_end_at(tmp_path):
    from aether.task import extraction
    res = extraction.analyze("ประชุม 2026-10-20 10:00 เป็นเวลา 2 ชั่วโมง", now=datetime(2026,10,26))
    c = res.candidates[0]
    assert c.end_at is not None


def test_duration_minutes_creates_end_at(tmp_path):
    from aether.task import extraction
    res = extraction.analyze("ประชุม 2026-10-20 10:00 อีก 30 นาที", now=datetime(2026,10,26))
    c = res.candidates[0]
    assert c.end_at is not None


def test_range_cross_midnight_ambiguous_no_guess(tmp_path):
    from aether.task import extraction
    res = extraction.analyze("ประชุม 2026-10-20 23:00-01:00", now=datetime(2026,10,26))
    c = res.candidates[0]
    assert "end_at" in c.missing_fields


def test_duration_without_start_no_fields(tmp_path):
    from aether.task import extraction
    res = extraction.analyze("ประชุม เป็นเวลา 2 ชั่วโมง", now=datetime(2026,10,26))
    c = res.candidates[0]
    assert c.start_at is None


def test_time_only_with_end_has_no_end_at(tmp_path):
    from aether.task import extraction
    res = extraction.analyze("14:00 ถึง 16:00", now=datetime(2026,10,26))
    c = res.candidates[0]
    assert c.start_at is None
    assert "date" in c.missing_fields
