"""Tests for Calendar endpoints — day / week / month views (P4).

API Contract v1.1: views come straight from the ScheduleEngine's
calendar_query functions and show ALL statuses (pending, completed,
cancelled). Timezone/tz values pass through unchanged.
"""

from __future__ import annotations

from datetime import date

from aether.task.models import ItemKind


def _task(wired, title, due_date, **extra):
    return wired.service.create(ItemKind.TASK, title, due_date=due_date, **extra)


def _event(wired, title, start_at, end_at, **extra):
    return wired.service.create(
        ItemKind.EVENT, title, start_at=start_at, end_at=end_at, **extra
    )


class TestDayView:
    def test_empty_day_shape(self, wired):
        response = wired.client.get(
            "/api/v1/calendar/day", params={"date": "2026-10-21"}
        )
        assert response.status_code == 200
        assert response.json() == {"date": "2026-10-21", "events": [], "tasks": []}

    def test_task_appears_only_on_its_due_date(self, wired):
        _task(wired, "Due tomorrow", "2026-10-22")
        on_day = wired.client.get(
            "/api/v1/calendar/day", params={"date": "2026-10-22"}
        ).json()
        assert [t["title"] for t in on_day["tasks"]] == ["Due tomorrow"]

        other_day = wired.client.get(
            "/api/v1/calendar/day", params={"date": "2026-10-21"}
        ).json()
        assert other_day["tasks"] == []

    def test_task_without_due_date_never_appears(self, wired):
        wired.service.create(ItemKind.TASK, "Floating")
        response = wired.client.get(
            "/api/v1/calendar/day", params={"date": "2026-10-21"}
        )
        assert response.json()["tasks"] == []

    def test_multi_day_event_covers_each_day(self, wired):
        _event(
            wired,
            "Conference",
            "2026-10-21T09:00:00+07:00",
            "2026-10-23T18:00:00+07:00",
        )
        for day, expected in [
            ("2026-10-21", True),
            ("2026-10-22", True),
            ("2026-10-23", True),
            ("2026-10-24", False),
        ]:
            view = wired.client.get(
                "/api/v1/calendar/day", params={"date": day}
            ).json()
            assert bool(view["events"]) is expected, day

    def test_calendar_shows_all_statuses(self, wired):
        """Locked decision: no status filtering in calendar views."""
        done = _task(wired, "Finished", "2026-10-21")
        bye = _task(wired, "Dropped", "2026-10-21")
        wired.service.complete(done.id)
        wired.service.cancel(bye.id)

        view = wired.client.get(
            "/api/v1/calendar/day", params={"date": "2026-10-21"}
        ).json()
        by_title = {t["title"]: t["status"] for t in view["tasks"]}
        assert by_title == {"Finished": "completed", "Dropped": "cancelled"}

    def test_timezone_passes_through(self, wired):
        """A UTC item keeps its own offset and local date."""
        _event(
            wired,
            "UTC sync",
            "2026-10-21T15:00:00",  # naive → attached to item tz
            "2026-10-21T16:00:00",
            tz="UTC",
        )
        view = wired.client.get(
            "/api/v1/calendar/day", params={"date": "2026-10-21"}
        ).json()
        assert len(view["events"]) == 1
        event = view["events"][0]
        assert event["tz"] == "UTC"
        assert event["start_at"].endswith("+00:00")
        assert event["start_at"].startswith("2026-10-21")

    def test_invalid_date_format_is_400(self, wired):
        response = wired.client.get(
            "/api/v1/calendar/day", params={"date": "21-10-2026"}
        )
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"


class TestWeekView:
    def test_week_spans_monday_to_sunday(self, wired):
        # 2026-10-21 is a Wednesday; the ISO week starts Monday 2026-10-19.
        _task(wired, "Midweek", "2026-10-21")
        response = wired.client.get(
            "/api/v1/calendar/week", params={"date": "2026-10-21"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["start_date"] == "2026-10-19"
        assert data["end_date"] == "2026-10-25"
        assert len(data["days"]) == 7
        assert [d["date"] for d in data["days"]] == [
            "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22",
            "2026-10-23", "2026-10-24", "2026-10-25",
        ]
        populated = [d for d in data["days"] if d["tasks"]]
        assert len(populated) == 1
        assert populated[0]["date"] == "2026-10-21"

    def test_empty_days_present_for_grid_rendering(self, wired):
        response = wired.client.get(
            "/api/v1/calendar/week", params={"date": "2026-10-21"}
        )
        for day in response.json()["days"]:
            assert set(day.keys()) == {"date", "events", "tasks"}


class TestMonthView:
    def test_month_metadata_and_day_count(self, wired):
        response = wired.client.get(
            "/api/v1/calendar/month", params={"year": 2026, "month": 10}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["year"] == 2026
        assert data["month"] == 10
        assert data["first_weekday"] == date(2026, 10, 1).weekday()
        assert len(data["days"]) == 31
        assert data["days"][0]["date"] == "2026-10-01"
        assert data["days"][-1]["date"] == "2026-10-31"

    def test_task_visible_in_month_grid(self, wired):
        _task(wired, "Month task", "2026-10-15")
        data = wired.client.get(
            "/api/v1/calendar/month", params={"year": 2026, "month": 10}
        ).json()
        day = next(d for d in data["days"] if d["date"] == "2026-10-15")
        assert [t["title"] for t in day["tasks"]] == ["Month task"]

    def test_invalid_month_is_400(self, wired):
        response = wired.client.get(
            "/api/v1/calendar/month", params={"year": 2026, "month": 13}
        )
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"
