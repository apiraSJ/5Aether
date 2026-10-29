import threading
import time

import pytest

from aether.task import drafts
from aether.task.drafts import DraftStore, DraftState, DraftExpiredError, DraftNotOpenError, DraftBusyError


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def test_create_open_expires():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, clock=c)
    from aether.task import extraction
    res = extraction.analyze("14:00", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    assert d.state == DraftState.OPEN
    assert d.expires_at == 2800


def test_get_expired():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=10, clock=c)
    from aether.task import extraction
    res = extraction.analyze("14:00", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    c.advance(20)
    with pytest.raises(DraftExpiredError):
        s.get(d.draft_id)


def test_discard_once():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, clock=c)
    from aether.task import extraction
    res = extraction.analyze("14:00", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    assert s.discard(d.draft_id) is True
    assert s.discard(d.draft_id) is False


def test_begin_confirm_twice_busy():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, clock=c)
    from aether.task import extraction
    res = extraction.analyze("พรุ่งนี้ ส่งรายงาน", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    token = s.begin_confirm(d.draft_id, [d.items[0].draft_item_id])
    with pytest.raises(DraftBusyError):
        s.begin_confirm(d.draft_id, [d.items[0].draft_item_id])


def test_begin_confirm_on_discard():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, clock=c)
    from aether.task import extraction
    res = extraction.analyze("14:00", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    s.discard(d.draft_id)
    with pytest.raises(DraftNotOpenError):
        s.begin_confirm(d.draft_id, [])


def test_finish_wrong_token():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, clock=c)
    from aether.task import extraction
    res = extraction.analyze("พรุ่งนี้ ส่งรายงาน", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    token = s.begin_confirm(d.draft_id, [d.items[0].draft_item_id])
    with pytest.raises(DraftBusyError):
        s.finish_confirm(d.draft_id, "bad", [])
    # stay in confirming state
    with pytest.raises(DraftBusyError):
        s.get(d.draft_id)
    d3 = s.finish_confirm(d.draft_id, token, ["item_x"])
    assert d3.state == DraftState.CONFIRMED


def test_finish_confirmed():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, clock=c)
    from aether.task import extraction
    res = extraction.analyze("พรุ่งนี้ ส่งรายงาน", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    token = s.begin_confirm(d.draft_id, [d.items[0].draft_item_id])
    d2 = s.finish_confirm(d.draft_id, token, ["item_123"])
    assert d2.state == DraftState.CONFIRMED
    assert d2.created_item_ids == ("item_123",)


def test_abort_confirm_back_to_open():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, clock=c)
    from aether.task import extraction
    res = extraction.analyze("14:00", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    token = s.begin_confirm(d.draft_id, [d.items[0].draft_item_id])
    s.abort_confirm(d.draft_id, token)
    d2 = s.get(d.draft_id)
    assert d2.state == DraftState.OPEN


def test_lease_takeover():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, confirm_lease_seconds=60, clock=c)
    from aether.task import extraction
    res = extraction.analyze("พรุ่งนี้ ส่งรายงาน", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    token1 = s.begin_confirm(d.draft_id, [d.items[0].draft_item_id])
    c.advance(61)
    # takeover
    token2 = s.begin_confirm(d.draft_id, [d.items[0].draft_item_id])
    assert token2 != token1
    with pytest.raises(DraftBusyError):
        s.finish_confirm(d.draft_id, token1, [])


def test_max_open_evict_lru_keep_confirming():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, max_open=2, clock=c)
    from aether.task import extraction
    r1 = extraction.analyze("14:00", now=__import__('datetime').datetime(2026,1,1))
    r2 = extraction.analyze("15:00", now=__import__('datetime').datetime(2026,1,1))
    r3 = extraction.analyze("16:00", now=__import__('datetime').datetime(2026,1,1))
    d1 = s.create(r1)
    d2 = s.create(r2)
    s.begin_confirm(d2.draft_id, [d2.items[0].draft_item_id])
    d3 = s.create(r3)  # should evict d1 (OPEN)
    with pytest.raises(DraftExpiredError):
        s.get(d1.draft_id)
    # d2 still confirming
    with pytest.raises(DraftBusyError):
        s.get(d2.draft_id)


def test_concurrent_begin_confirm():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, clock=c)
    from aether.task import extraction
    res = extraction.analyze("พรุ่งนี้ ส่งรายงาน", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    results = []
    def try_begin():
        try:
            t = s.begin_confirm(d.draft_id, [d.items[0].draft_item_id])
            results.append(('ok', t))
        except Exception as e:
            results.append(('err', type(e).__name__))
    threads = [threading.Thread(target=try_begin) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    oks = [r for r in results if r[0] == 'ok']
    errs = [r for r in results if r[0] == 'err']
    assert len(oks) == 1
    assert len(errs) == 19


def test_analyze_again_after_discard_new_draft():
    c = FakeClock(1000)
    s = DraftStore(ttl_seconds=1800, clock=c)
    from aether.task import extraction
    res = extraction.analyze("14:00", now=__import__('datetime').datetime(2026,1,1))
    d = s.create(res)
    s.discard(d.draft_id)
    d2 = s.create(res)
    assert d2.draft_id != d.draft_id
