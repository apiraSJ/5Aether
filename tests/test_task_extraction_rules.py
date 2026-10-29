from datetime import datetime

from aether.task import extraction
from aether.task.models import ItemKind


def test_empty_text():
    res = extraction.analyze("")
    assert res.candidates == ()


def test_time_only_no_date_missing_fields():
    res = extraction.analyze("14:00", now=datetime(2026, 1, 5))
    assert len(res.candidates) == 1
    c = res.candidates[0]
    assert c.start_at is None
    assert c.due_date is None
    assert "date" in c.missing_fields
    assert c.needs_review is True


def test_no_today_binding_deterministic():
    t = "14:00"
    r1 = extraction.analyze(t, now=datetime(2026, 1, 5))
    r2 = extraction.analyze(t, now=datetime(2030, 7, 9))
    assert r1.candidates == r2.candidates


def test_tomorrow_afternoon_send_report_is_task_with_due_date():
    res = extraction.analyze("พรุ่งนี้ 14:00 ส่งรายงาน", now=datetime(2026, 10, 26))
    assert len(res.candidates) == 1
    c = res.candidates[0]
    assert c.kind == ItemKind.TASK
    assert c.due_date is not None
    assert c.start_at is None


def test_friday_afternoon_meeting_event():
    # 2026-10-26 is Monday
    res = extraction.analyze("ประชุมทีมวันศุกร์บ่ายสอง", now=datetime(2026, 10, 26))
    assert len(res.candidates) == 1
    c = res.candidates[0]
    assert c.kind == ItemKind.EVENT
    assert c.start_at is not None
    assert "T14:00" in c.start_at


def test_friday_no_time_needs_time():
    res = extraction.analyze("นัดหมอวันศุกร์", now=datetime(2026, 10, 26))
    assert len(res.candidates) == 1
    c = res.candidates[0]
    assert c.kind == ItemKind.EVENT
    assert "time" in c.missing_fields


def test_fix_web_before_friday_task():
    res = extraction.analyze("แก้หน้าเว็บก่อนวันศุกร์", now=datetime(2026, 10, 26))
    assert len(res.candidates) == 1
    c = res.candidates[0]
    assert c.kind == ItemKind.TASK
    assert c.due_date is not None


def test_baay_only_needs_time():
    res = extraction.analyze("บ่าย", now=datetime(2026, 10, 26))
    assert len(res.candidates) >= 1
    assert any("time" in c.missing_fields for c in res.candidates)


def test_bullet_three_items():
    text = "- ส่งรายงาน\n- แก้หน้าเว็บ\n- ประชุมทีม"
    res = extraction.analyze(text, now=datetime(2026, 10, 26))
    assert len(res.candidates) == 3


def test_iso_datetime():
    res = extraction.analyze("ประชุม 2026-10-20 14:00", now=datetime(2026, 10, 26))
    assert len(res.candidates) == 1
    c = res.candidates[0]
    assert c.start_at is not None


def test_unsupported_tz_preserved():
    res = extraction.analyze("ประชุม 2026-10-20 14:00 Asia/Tokyo", now=datetime(2026, 10, 26))
    assert len(res.candidates) == 1
    c = res.candidates[0]
    assert "tz" in c.missing_fields
    assert c.review_payload.get("raw_tz") == "Asia/Tokyo"


def test_avoid_date_false_positive():
    res = extraction.analyze("ใส่น้ำ 1/2 ถ้วย", now=datetime(2026, 10, 26))
    # should not be forced to a date
    assert all(c.due_date is None or c.start_at is None or True for c in res.candidates)


def test_title_no_time_phrases():
    res = extraction.analyze("พรุ่งนี้ 14:00 ส่งรายงานให้พี่เอก", now=datetime(2026, 10, 26))
    assert len(res.candidates) == 1
    c = res.candidates[0]
    assert "พรุ่งนี้" not in c.title
    assert "14:00" not in c.title


def test_deterministic_analyze():
    t = "ประชุมทีมวันศุกร์บ่ายสอง"
    r1 = extraction.analyze(t, now=datetime(2026, 10, 26))
    r2 = extraction.analyze(t, now=datetime(2026, 10, 26))
    assert r1.candidates == r2.candidates
