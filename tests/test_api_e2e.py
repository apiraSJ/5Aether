"""End-to-end tests: HTTP API → ScheduleService → SQLite, across restarts.

Covers the Mark-1 Prototype acceptance paths (delivery step 4):
- full user workflows through the API only,
- timezone/R1/R6 regressions at the API boundary,
- transaction rollback (a rejected write leaves no trace),
- persistence across a real web-app reboot (stop, boot, serve again).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from aether.__main__ import WEB_CONFIG


# ── helpers ─────────────────────────────────────────────────────────


def _write_web_config(tmp_path: Path) -> Path:
    """web.yaml copy pointing at a temp database (never the real one)."""
    db_path = str(tmp_path / "tasks.db").replace("\\", "/")
    text = WEB_CONFIG.read_text(encoding="utf-8")
    text = text.replace('db_path: "data/tasks.db"', f'db_path: "{db_path}"')
    cfg = tmp_path / "web.yaml"
    cfg.write_text(text, encoding="utf-8")
    return cfg


def _boot_web(tmp_path: Path):
    from aether.app import AetherApp

    app = AetherApp(config_path=str(_write_web_config(tmp_path)))
    app.boot()
    return app


# ── full user workflows ────────────────────────────────────────────


class TestTaskWorkflow:
    def test_create_edit_complete_history_delete(self, wired):
        client = wired.client

        # Create
        created = client.post(
            "/api/v1/tasks",
            json={"kind": "task", "title": "Ship prototype", "due_date": "2026-10-25"},
        )
        assert created.status_code == 201
        item = created.json()
        assert item["status"] == "pending"

        # It shows up in the list the UI renders from
        listed = client.get("/api/v1/tasks").json()
        assert any(i["id"] == item["id"] for i in listed["items"])

        # Edit (optimistic concurrency with the freshly-read updated_at)
        renamed = client.patch(
            f"/api/v1/tasks/{item['id']}",
            json={"title": "Ship prototype v2"},
            headers={"If-Match": str(item["updated_at"])},
        )
        assert renamed.status_code == 200

        # Complete
        done = client.post(f"/api/v1/tasks/{item['id']}/complete")
        assert done.status_code == 200
        assert done.json()["status"] == "completed"

        # Full audit trail through the API
        history = client.get(f"/api/v1/tasks/{item['id']}/history").json()
        actions = [e["action"] for e in history["entries"]]
        assert actions == ["completed", "updated", "created"]

        # Delete → gone from reads, history survives
        assert client.delete(f"/api/v1/tasks/{item['id']}").status_code == 204
        assert client.get(f"/api/v1/tasks/{item['id']}").status_code == 404
        after = client.get(f"/api/v1/tasks/{item['id']}/history").json()
        assert after["count"] == 4  # + deleted entry

    def test_event_flows_into_calendar_and_cancel_keeps_it_visible(self, wired):
        client = wired.client
        event = client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "Planning",
                "start_at": "2026-10-24T09:00:00+07:00",
                "end_at": "2026-10-25T12:00:00+07:00",
            },
        ).json()

        # Visible on both covered days
        for day in ("2026-10-24", "2026-10-25"):
            view = client.get("/api/v1/calendar/day", params={"date": day}).json()
            assert [e["title"] for e in view["events"]] == ["Planning"]

        # Cancel with a reason; calendar still shows it (all statuses)
        cancelled = client.post(
            f"/api/v1/tasks/{event['id']}/cancel?reason=double+booking"
        )
        assert cancelled.status_code == 200
        view = client.get("/api/v1/calendar/day", params={"date": "2026-10-24"}).json()
        assert view["events"][0]["status"] == "cancelled"

        history = client.get(f"/api/v1/tasks/{event['id']}/history").json()
        entry = next(e for e in history["entries"] if e["action"] == "cancelled")
        assert entry["note"] == "double booking"


# ── transaction rollback ────────────────────────────────────────────


class TestTransactionRollback:
    def test_rejected_update_leaves_no_trace(self, wired):
        client = wired.client
        event = client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "Stable",
                "start_at": "2026-10-21T10:00:00+07:00",
                "end_at": "2026-10-21T11:00:00+07:00",
            },
        ).json()
        history_before = client.get(
            f"/api/v1/tasks/{event['id']}/history"
        ).json()["count"]

        # Inverted chronology passes the request schema but fails inside
        # the service, inside its transaction.
        response = client.patch(
            f"/api/v1/tasks/{event['id']}",
            json={
                "start_at": "2026-10-21T23:00:00+07:00",  # 16:00Z
                "end_at": "2026-10-21T23:30:00+09:00",    # 14:30Z — earlier
            },
            headers={"If-Match": str(event["updated_at"])},
        )
        assert response.status_code == 400

        # Nothing changed: same values, same updated_at, no history entry.
        current = client.get(f"/api/v1/tasks/{event['id']}").json()
        assert current["start_at"] == event["start_at"]
        assert current["end_at"] == event["end_at"]
        assert current["updated_at"] == event["updated_at"]
        history_after = client.get(
            f"/api/v1/tasks/{event['id']}/history"
        ).json()["count"]
        assert history_after == history_before

    def test_rejected_create_leaves_no_item(self, wired):
        client = wired.client
        before = client.get("/api/v1/tasks").json()["count"]
        response = client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "Phantom",
                "start_at": "2026-10-21",  # R6: date-only for timed item
                "end_at": "2026-10-21",
            },
        )
        assert response.status_code == 400
        after = client.get("/api/v1/tasks").json()["count"]
        assert after == before


# ── timezone regression at the API boundary ────────────────────────


class TestTimezoneRegression:
    def test_offsets_survive_create_and_read(self, wired):
        client = wired.client
        bkk = client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "Bangkok",
                "start_at": "2026-10-21T10:00:00",  # naive → item tz attached
                "end_at": "2026-10-21T11:00:00",
                "tz": "Asia/Bangkok",
            },
        ).json()
        utc = client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "London",
                "start_at": "2026-10-21T10:00:00",
                "end_at": "2026-10-21T11:00:00",
                "tz": "UTC",
            },
        ).json()

        assert bkk["start_at"] == "2026-10-21T10:00:00+07:00"
        assert bkk["tz"] == "Asia/Bangkok"
        assert utc["start_at"] == "2026-10-21T10:00:00+00:00"
        assert utc["tz"] == "UTC"

        # Re-read through a different endpoint — values unchanged.
        reread = client.get(f"/api/v1/tasks/{utc['id']}").json()
        assert reread["start_at"] == "2026-10-21T10:00:00+00:00"

    def test_mixed_offset_chronology_still_enforced(self, wired):
        """R1 holds at the API entry point (instant, not string, order)."""
        response = wired.client.post(
            "/api/v1/tasks",
            json={
                "kind": "event",
                "title": "Inverted",
                "start_at": "2026-10-21T23:00:00+07:00",  # 16:00Z
                "end_at": "2026-10-21T23:30:00+09:00",     # 14:30Z
            },
        )
        assert response.status_code == 400


# ── restart persistence (real web-app lifecycle) ───────────────────


class TestRestartPersistence:
    def test_items_survive_full_web_app_reboot(self, tmp_path, monkeypatch):
        """run() → create → stop; reboot → run() again → items still there.

        Exercises the real lifecycle: plugin start (repo open), API writes,
        plugin stop (repo close), AetherApp shutdown, then a fresh boot
        reading the same database file.
        """
        created_payload = {}

        def make_serve(operations):
            def fake_uvicorn_run(api_app, *, host, port, log_level):
                client = TestClient(api_app, base_url="http://localhost")
                operations(client)
            return fake_uvicorn_run

        def create_and_verify_first_run(client):
            response = client.post(
                "/api/v1/tasks",
                json={
                    "kind": "event",
                    "title": "Survives reboot",
                    "start_at": "2026-10-30T14:00:00",
                    "end_at": "2026-10-30T15:00:00",
                    "tz": "Asia/Bangkok",
                },
            )
            assert response.status_code == 201
            created_payload.update(response.json())

        from aether.api.server import run

        # First life of the app
        monkeypatch.setattr(uvicorn, "run", make_serve(create_and_verify_first_run))
        app1 = _boot_web(tmp_path)
        assert run(app1) == 0
        assert app1.is_booted is False

        def verify_second_run(client):
            fetched = client.get(f"/api/v1/tasks/{created_payload['id']}")
            assert fetched.status_code == 200
            item = fetched.json()
            assert item["title"] == "Survives reboot"
            # Offsets intact across the restart (tz regression + persistence)
            assert item["start_at"] == "2026-10-30T14:00:00+07:00"
            assert item["tz"] == "Asia/Bangkok"
            # And the calendar sees it too
            view = client.get(
                "/api/v1/calendar/day", params={"date": "2026-10-30"}
            ).json()
            assert [e["title"] for e in view["events"]] == ["Survives reboot"]

        # Second life of the app — fresh boot, same database
        monkeypatch.setattr(uvicorn, "run", make_serve(verify_second_run))
        app2 = _boot_web(tmp_path)
        assert run(app2) == 0
