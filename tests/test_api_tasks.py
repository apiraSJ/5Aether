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


# ── POST /api/v1/tasks (P2 — Create) ───────────────────────────────


class TestCreateTasks:
    def test_minimal_task_uses_contract_defaults(self, wired):
        response = wired.client.post(
            "/api/v1/tasks", json={"kind": "task", "title": "Write report"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Write report"
        assert data["status"] == "pending"
        assert data["internal_status"] == "confirmed"
        assert data["tz"] == "Asia/Bangkok"
        assert data["source"] == "manual"
        assert isinstance(data["updated_at"], float)

    def test_client_cannot_set_internal_status(self, wired):
        """internal_status is locked to 'confirmed' server-side."""
        response = wired.client.post(
            "/api/v1/tasks",
            json={
                "kind": "task",
                "title": "Sneaky",
                "internal_status": "needs_confirmation",
            },
        )
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"

    def test_client_cannot_set_server_controlled_fields(self, wired):
        """id/status/created_at/updated_at are server-controlled."""
        for field, value in [
            ("id", "custom-id"),
            ("status", "completed"),
            ("created_at", 1.0),
            ("updated_at", 2.0),
        ]:
            response = wired.client.post(
                "/api/v1/tasks",
                json={"kind": "task", "title": "Locked", field: value},
            )
            assert response.status_code == 400, f"{field} must be rejected"
            assert response.json()["error"] == "validation_error"

    def test_unknown_field_rejected(self, wired):
        response = wired.client.post(
            "/api/v1/tasks",
            json={"kind": "task", "title": "Mystery", "colour": "blue"},
        )
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"

    def test_event_timed_range_accepted(self, wired):
        response = wired.client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "1:1",
                "start_at": "2026-10-21T10:00:00+07:00",
                "end_at": "2026-10-21T10:30:00+07:00",
            },
        )
        assert response.status_code == 201
        assert response.json()["kind"] == "event"

    def test_r6_date_only_start_rejected_for_timed_item(self, wired):
        """R6: date-only timestamps are rejected for timed items."""
        response = wired.client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "All day? no",
                "start_at": "2026-10-21",
                "end_at": "2026-10-21",
            },
        )
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"

    def test_r1_rejects_instant_inversion_hidden_by_string_order(self, wired):
        """R1: chronology uses instants, not string comparison.

        end_at is lexicographically *after* start_at ('23:30' > '23:00')
        but in real instants it is 90 minutes *earlier* (+09:00 vs +07:00)
        — the API must reject it.
        """
        response = wired.client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "Inverted instants",
                "start_at": "2026-10-21T23:00:00+07:00",  # 16:00Z
                "end_at": "2026-10-21T23:30:00+09:00",    # 14:30Z
            },
        )
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"

    def test_r1_accepts_instant_order_hidden_by_string_order(self, wired):
        """R1: end_at string looks earlier but its instant is later — valid."""
        response = wired.client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "Offset leap",
                "start_at": "2026-10-21T20:00:00+03:00",  # 17:00Z
                "end_at": "2026-10-21T19:00:00+01:00",    # 18:00Z
            },
        )
        assert response.status_code == 201


# ── PATCH /api/v1/tasks/{id} (P2 — Edit) ───────────────────────────


class TestPatchTasks:
    def _create(self, wired, **extra):
        body = {"kind": "task", "title": "Original", **extra}
        return wired.client.post("/api/v1/tasks", json=body).json()

    def test_patch_with_fresh_if_match_succeeds(self, wired):
        item = self._create(wired)
        response = wired.client.patch(
            f"/api/v1/tasks/{item['id']}",
            json={"title": "Renamed"},
            headers={"If-Match": str(item["updated_at"])},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Renamed"
        assert data["updated_at"] > item["updated_at"]

    def test_patch_with_stale_if_match_conflicts(self, wired):
        item = self._create(wired)
        # Someone else edits first…
        wired.client.patch(
            f"/api/v1/tasks/{item['id']}",
            json={"title": "Their edit"},
            headers={"If-Match": str(item["updated_at"])},
        )
        # …our stale write must not silently overwrite it.
        response = wired.client.patch(
            f"/api/v1/tasks/{item['id']}",
            json={"title": "Our stale edit"},
            headers={"If-Match": str(item["updated_at"])},
        )
        assert response.status_code == 409
        body = response.json()
        assert body["error"] == "conflict"
        # Nothing was written.
        current = wired.client.get(f"/api/v1/tasks/{item['id']}").json()
        assert current["title"] == "Their edit"

    def test_patch_without_if_match_is_allowed(self, wired):
        """Contract v1.1: the concurrency check runs when If-Match is sent."""
        item = self._create(wired)
        response = wired.client.patch(
            f"/api/v1/tasks/{item['id']}", json={"title": "No guard"}
        )
        assert response.status_code == 200
        assert response.json()["title"] == "No guard"

    def test_patch_malformed_if_match_is_400(self, wired):
        item = self._create(wired)
        response = wired.client.patch(
            f"/api/v1/tasks/{item['id']}",
            json={"title": "x"},
            headers={"If-Match": "not-a-float"},
        )
        assert response.status_code == 400

    def test_patch_rejects_unknown_field(self, wired):
        item = self._create(wired)
        response = wired.client.patch(
            f"/api/v1/tasks/{item['id']}", json={"colour": "blue"}
        )
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"

    def test_patch_rejects_internal_status(self, wired):
        item = self._create(wired)
        response = wired.client.patch(
            f"/api/v1/tasks/{item['id']}",
            json={"internal_status": "needs_confirmation"},
        )
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"

    def test_patch_rejects_immutable_kind(self, wired):
        item = self._create(wired)
        response = wired.client.patch(
            f"/api/v1/tasks/{item['id']}", json={"kind": "event"}
        )
        assert response.status_code == 400

    def test_patch_rejects_null_title(self, wired):
        item = self._create(wired)
        response = wired.client.patch(
            f"/api/v1/tasks/{item['id']}", json={"title": None}
        )
        assert response.status_code == 400

    def test_patch_null_owner_clears_field(self, wired):
        item = self._create(wired, owner="alice")
        response = wired.client.patch(
            f"/api/v1/tasks/{item['id']}", json={"owner": None}
        )
        assert response.status_code == 200
        assert response.json()["owner"] is None

    def test_patch_unknown_item_is_404(self, wired):
        response = wired.client.patch(
            "/api/v1/tasks/no-such-id", json={"title": "x"}
        )
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"

    def test_patch_empty_body_is_400(self, wired):
        item = self._create(wired)
        response = wired.client.patch(f"/api/v1/tasks/{item['id']}", json={})
        assert response.status_code == 400
        assert response.json()["error"] == "validation_error"
