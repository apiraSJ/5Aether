"""Tests for Task read endpoints — GET /api/v1/tasks, GET /api/v1/tasks/{id}.

API Contract v1.1 (P1 — Task List slice): the API is a thin adapter over the
shared ScheduleService; responses follow the Contract shape and errors use
the ``{error, message, detail}`` schema. Data is seeded through the real
service so list/filter behavior is proven against the Schedule Engine.
"""

from __future__ import annotations

from aether.task.models import ItemKind


def _seed(wired):
    """Seed one task, one event, and one completed task via ScheduleService."""
    svc = wired.service
    task = svc.create(ItemKind.TASK, "Buy milk", due_date="2026-10-21")
    event = svc.create(
        ItemKind.EVENT,
        "Standup",
        start_at="2026-10-21T10:00:00+07:00",
        end_at="2026-10-21T10:15:00+07:00",
    )
    done = svc.create(ItemKind.TASK, "Filed report", due_date="2026-10-20")
    svc.complete(done.id)
    return task, event, done


class TestListTasks:
    def test_empty_list_contract_shape(self, wired):
        response = wired.client.get("/api/v1/tasks")
        assert response.status_code == 200
        assert response.json() == {"items": [], "count": 0}

    def test_returns_all_seeded_items(self, wired):
        _seed(wired)
        response = wired.client.get("/api/v1/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert len(data["items"]) == 3
        titles = {i["title"] for i in data["items"]}
        assert titles == {"Buy milk", "Standup", "Filed report"}

    def test_items_carry_contract_fields(self, wired):
        _seed(wired)
        items = wired.client.get("/api/v1/tasks").json()["items"]
        required = {
            "id", "kind", "title", "description", "due_date", "start_at",
            "end_at", "all_day", "tz", "owner", "source", "status",
            "internal_status", "created_at", "updated_at",
        }
        for item in items:
            assert required <= set(item.keys())
            assert item["internal_status"] == "confirmed"
            assert item["status"] in ("pending", "completed", "cancelled")
            assert isinstance(item["updated_at"], float)

    def test_filter_by_kind(self, wired):
        _seed(wired)
        response = wired.client.get("/api/v1/tasks", params={"kind": "event"})
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["items"][0]["kind"] == "event"

    def test_filter_by_status(self, wired):
        _seed(wired)
        response = wired.client.get("/api/v1/tasks", params={"status": "completed"})
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        assert data["items"][0]["title"] == "Filed report"

    def test_invalid_status_filter_is_400_validation_error(self, wired):
        """FastAPI 422 is mapped to Contract 400 validation_error."""
        response = wired.client.get("/api/v1/tasks", params={"status": "bogus"})
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"


class TestGetTask:
    def test_returns_single_item(self, wired):
        task, _, _ = _seed(wired)
        response = wired.client.get(f"/api/v1/tasks/{task.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task.id
        assert data["title"] == "Buy milk"
        assert data["kind"] == "task"
        assert data["due_date"] == "2026-10-21"
        assert data["tz"] == "Asia/Bangkok"

    def test_completed_status_visible_on_read(self, wired):
        _, _, done = _seed(wired)
        data = wired.client.get(f"/api/v1/tasks/{done.id}").json()
        assert data["status"] == "completed"

    def test_unknown_id_is_404_contract_shape(self, wired):
        response = wired.client.get("/api/v1/tasks/no-such-id")
        assert response.status_code == 404
        body = response.json()
        assert body["error"] == "not_found"
        assert "message" in body
        assert "detail" in body
