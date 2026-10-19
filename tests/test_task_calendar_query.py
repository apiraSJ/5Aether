"""Phase 2 tests — calendar_query pure functions.

Display rules: tasks on due_date only; events on every day their date
range covers (interval overlap, midnight end does not spill); empty days
always present; string date comparison only (no datetime arithmetic).
"""

from __future__ import annotations

import pytest

from aether.task.calendar_query import (
    day_view,
    event_covers_dates,
    find_overlapping_events,
    items_on_day,
    month_view,
    views_to_dicts,
    week_view,
)
from aether.task.models import ItemKind, TaskItem


def task(**kw) -> TaskItem:
    defaults = dict(kind=ItemKind.TASK, title="t", created_at=1.0, updated_at=1.0)
    defaults.update(kw)
    return TaskItem(**defaults)


def event(**kw) -> TaskItem:
    defaults = dict(kind=ItemKind.EVENT, title="e", created_at=1.0, updated_at=1.0)
    defaults.update(kw)
    return TaskItem(**defaults)


class TestEventCoversDates:
    def test_no_end_at_single_day(self):
        item = event(start_at="2026-10-20T09:00:00+07:00")
        assert event_covers_dates(item) == ("2026-10-20", "2026-10-20")

    def test_all_day_span(self):
        item = event(all_day=True, start_at="2026-10-20", end_at="2026-10-22")
        assert event_covers_dates(item) == ("2026-10-20", "2026-10-22")

    def test_timed_same_day(self):
        item = event(start_at="2026-10-20T09:00:00+07:00", end_at="2026-10-20T18:00:00+07:00")
        assert event_covers_dates(item) == ("2026-10-20", "2026-10-20")

    def test_timed_multiday(self):
        item = event(start_at="2026-10-20T09:00:00+07:00", end_at="2026-10-22T12:00:00+07:00")
        assert event_covers_dates(item) == ("2026-10-20", "2026-10-22")

    def test_midnight_end_does_not_spill(self):
        item = event(start_at="2026-10-20T18:00:00+07:00", end_at="2026-10-21T00:00:00+07:00")
        assert event_covers_dates(item) == ("2026-10-20", "2026-10-20")

    def test_midnight_end_never_before_start(self):
        item = event(start_at="2026-10-22T00:00:00+07:00", end_at="2026-10-22T00:00:00+07:00")
        assert event_covers_dates(item) == ("2026-10-22", "2026-10-22")

    def test_foreign_offset_uses_own_local_date(self):
        item = event(start_at="2026-10-20T00:30:00+09:00")
        assert event_covers_dates(item) == ("2026-10-20", "2026-10-20")

    def test_no_start_returns_empty(self):
        assert event_covers_dates(event()) == ("", "")


class TestItemsOnDay:
    def test_task_on_due_date_only(self):
        items = [task(due_date="2026-10-20")]
        on = items_on_day(items, "2026-10-20")
        off = items_on_day(items, "2026-10-21")
        assert len(on["tasks"]) == 1
        assert off["tasks"] == []

    def test_task_without_due_date_never_appears(self):
        items = [task()]
        for day in ("2026-10-20", "2026-10-21", "2026-11-01"):
            assert items_on_day(items, day)["tasks"] == []

    def test_event_on_each_covered_day(self):
        items = [event(start_at="2026-10-20T09:00:00+07:00", end_at="2026-10-22T12:00:00+07:00")]
        for day in ("2026-10-20", "2026-10-21", "2026-10-22"):
            assert len(items_on_day(items, day)["events"]) == 1
        for day in ("2026-10-19", "2026-10-23"):
            assert items_on_day(items, day)["events"] == []

    def test_event_midnight_end_stays_on_start_day(self):
        items = [event(start_at="2026-10-20T18:00:00+07:00", end_at="2026-10-21T00:00:00+07:00")]
        assert len(items_on_day(items, "2026-10-20")["events"]) == 1
        assert items_on_day(items, "2026-10-21")["events"] == []

    def test_all_day_event_single_day_when_no_end(self):
        items = [event(all_day=True, start_at="2026-10-20")]
        assert len(items_on_day(items, "2026-10-20")["events"]) == 1
        assert items_on_day(items, "2026-10-21")["events"] == []

    def test_events_before_tasks_sorted_by_time(self):
        items = [
            task(due_date="2026-10-20", title="b-task"),
            task(due_date="2026-10-20", title="a-task"),
            event(start_at="2026-10-20T14:00:00+07:00", title="later"),
            event(start_at="2026-10-20T09:00:00+07:00", title="earlier"),
        ]
        day = items_on_day(items, "2026-10-20")
        assert [e.title for e in day["events"]] == ["earlier", "later"]
        assert [t.title for t in day["tasks"]] == ["a-task", "b-task"]

    def test_empty_day(self):
        day = items_on_day([], "2026-10-20")
        assert day == {"events": [], "tasks": []}


class TestDayView:
    def test_shape(self):
        items = [task(due_date="2026-10-20", title="x")]
        view = day_view(items, "2026-10-20")
        assert view["date"] == "2026-10-20"
        assert [t.title for t in view["tasks"]] == ["x"]
        assert view["events"] == []


class TestWeekView:
    def test_snaps_to_monday(self):
        view = week_view([], "2026-10-21")  # Wednesday
        assert view["start_date"] == "2026-10-19"  # that week's Monday
        assert view["end_date"] == "2026-10-25"
        assert len(view["days"]) == 7

    def test_all_days_present_including_empty(self):
        view = week_view([], "2026-10-19")
        assert [d["date"] for d in view["days"]] == [
            "2026-10-19", "2026-10-20", "2026-10-21",
            "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25",
        ]
        assert all(d["events"] == [] and d["tasks"] == [] for d in view["days"])

    def test_items_visible_across_week(self):
        items = [
            task(due_date="2026-10-19", title="mon"),
            task(due_date="2026-10-25", title="sun"),
            event(start_at="2026-10-21T09:00:00+07:00", title="wed"),
        ]
        view = week_view(items, "2026-10-22")
        by_date = {d["date"]: d for d in view["days"]}
        assert [t.title for t in by_date["2026-10-19"]["tasks"]] == ["mon"]
        assert [t.title for t in by_date["2026-10-25"]["tasks"]] == ["sun"]
        assert [e.title for e in by_date["2026-10-21"]["events"]] == ["wed"]


class TestMonthView:
    def test_october_2026(self):
        view = month_view([], 2026, 10)
        assert view["year"] == 2026
        assert view["month"] == 10
        assert view["first_weekday"] == 3  # 2026-10-01 is a Thursday
        assert len(view["days"]) == 31
        assert view["days"][0]["date"] == "2026-10-01"
        assert view["days"][-1]["date"] == "2026-10-31"

    def test_february_non_leap(self):
        view = month_view([], 2026, 2)
        assert len(view["days"]) == 28

    def test_invalid_month_raises(self):
        with pytest.raises(ValueError):
            month_view([], 2026, 13)

    def test_invalid_year_raises(self):
        with pytest.raises(ValueError):
            month_view([], 0, 1)

    def test_items_bucketed(self):
        items = [task(due_date="2026-10-05", title="early"), task(due_date="2026-10-30", title="late")]
        view = month_view(items, 2026, 10)
        by_date = {d["date"]: d for d in view["days"]}
        assert [t.title for t in by_date["2026-10-05"]["tasks"]] == ["early"]
        assert [t.title for t in by_date["2026-10-30"]["tasks"]] == ["late"]


class TestFindOverlappingEvents:
    def test_overlap(self):
        items = [event(id="item_1", start_at="2026-10-20T09:00:00+07:00", end_at="2026-10-22T12:00:00+07:00")]
        hits = find_overlapping_events(items, "2026-10-21T00:00:00+07:00", "2026-10-21T23:59:00+07:00")
        assert [i.id for i in hits] == ["item_1"]

    def test_no_overlap(self):
        items = [event(id="item_1", start_at="2026-10-20T09:00:00+07:00")]
        assert find_overlapping_events(items, "2026-11-01T00:00:00+07:00", "2026-11-02T00:00:00+07:00") == []

    def test_end_at_none_single_day_window(self):
        items = [event(id="item_1", start_at="2026-10-20T09:00:00+07:00")]
        assert find_overlapping_events(items, "2026-10-20T12:00:00+07:00") != []
        assert find_overlapping_events(items, "2026-10-21T12:00:00+07:00") == []

    def test_exclude_id(self):
        items = [event(id="item_1", start_at="2026-10-20T09:00:00+07:00")]
        assert find_overlapping_events(items, "2026-10-20T00:00:00+07:00", exclude_id="item_1") == []

    def test_tasks_ignored(self):
        items = [task(id="item_t", due_date="2026-10-20")]
        assert find_overlapping_events(items, "2026-10-20T00:00:00+07:00") == []

    def test_sorted_by_start(self):
        items = [
            event(id="late", start_at="2026-10-20T14:00:00+07:00"),
            event(id="early", start_at="2026-10-20T09:00:00+07:00"),
        ]
        hits = find_overlapping_events(items, "2026-10-20T00:00:00+07:00")
        assert [i.id for i in hits] == ["early", "late"]


class TestViewsToDicts:
    def test_day_serialized(self):
        items = [task(id="item_1", due_date="2026-10-20", title="x")]
        out = views_to_dicts(day_view(items, "2026-10-20"))
        assert out["date"] == "2026-10-20"
        assert out["tasks"][0]["id"] == "item_1"
        assert out["tasks"][0]["kind"] == "task"

    def test_month_serialized_no_items_left(self):
        items = [event(id="item_1", start_at="2026-10-20T09:00:00+07:00", title="e")]
        out = views_to_dicts(month_view(items, 2026, 10))
        assert "days" in out
        assert all(isinstance(d, dict) for d in out["days"])
        flat = [i for d in out["days"] for i in d["events"]]
        assert [i["id"] for i in flat] == ["item_1"]

    def test_week_serialized(self):
        out = views_to_dicts(week_view([task(due_date="2026-10-19", title="m")], "2026-10-21"))
        assert out["start_date"] == "2026-10-19"
        assert len(out["days"]) == 7
