"""Phase 2 tests — TaskPlugin lifecycle, 6 commands, post-commit events.

Event rule under test: TASK_* events publish only after the ScheduleService
transaction commits (service commits before returning, so success handlers
publish post-commit by construction). Failures raise ScheduleError, roll
back atomically, return {"ok": False} and publish nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.command_registry import CommandRegistry
from aether.core.event_bus_v2 import EventBus
from aether.core.event_type import EventType
from aether.core.service_container import ServiceContainer
from aether.plugins.task_plugin import TaskPlugin
from aether.task.models import ItemKind, ItemStatus
from aether.task.service import ScheduleService

TASK_TOPICS = (
    "task.ready",
    "task.created",
    "task.updated",
    "task.completed",
    "task.cancelled",
)


class _FakeConfig:
    def __init__(self, values=None):
        self._values = values or {}

    def get(self, key, default=None):
        return self._values.get(key, default)


def _container_for(db_path):
    container = ServiceContainer()
    container.register_instance("event_bus", EventBus(queued=False))
    container.register_instance("command_bus", CommandBus())
    container.register_instance("command_registry", CommandRegistry())
    container.register_instance("config", _FakeConfig({"task.db_path": db_path}))
    return container


def _dispatch(container, name, params):
    return container.resolve("command_bus").dispatch_sync(
        Command(name=name, source="test", params=params)
    )


@pytest.fixture
def env(tmp_path):
    db_path = str(tmp_path / "tasks.db")
    container = _container_for(db_path)
    plugin = TaskPlugin()
    events = []
    bus = container.resolve("event_bus")
    for topic in TASK_TOPICS:
        bus.subscribe(topic, lambda e: events.append(e))
    plugin.initialize(container)
    plugin.start()
    yield plugin, container, events, db_path
    plugin.stop()


def _event_types(events):
    return [e.type.value for e in events]


def _history_count(container, item_id):
    service = container.resolve("schedule_service")
    return len(service.history(item_id))


class TestLifecycle:
    def test_name_and_metadata(self, env):
        plugin, container, _, _ = env
        assert plugin.name == "task_plugin"
        meta = plugin.metadata
        assert meta.category == "task"
        assert meta.commands == [
            "task.create",
            "task.list",
            "task.complete",
            "task.cancel",
            "task.update",
            "task.calendar",
        ]

    def test_initialize_registers_shared_services(self, env):
        plugin, container, _, _ = env
        assert container.resolve("schedule_service") is plugin.schedule_service
        assert isinstance(plugin.schedule_service, ScheduleService)
        assert container.has("schedule_repository")
        assert container.has("calendar_query")

    def test_commands_registered_on_bus_and_registry(self, env):
        _, container, _, _ = env
        registry = container.resolve("command_registry")
        for name in ("task.create", "task.list", "task.complete", "task.cancel", "task.update", "task.calendar"):
            assert registry.is_registered(name), name

    def test_start_opens_repo_and_publishes_ready(self, env):
        plugin, _, events, db_path = env
        assert plugin.is_ready() is True
        assert _event_types(events) == ["task.ready"]
        payload = events[0].payload
        assert payload["db_path"] == db_path
        assert payload["items"] == 0

    def test_stop_closes_repo(self, env):
        plugin, _, _, _ = env
        plugin.stop()
        assert plugin.is_ready() is False

    def test_restart_preserves_data(self, env):
        plugin, container, _, db_path = env
        created = _dispatch(container, "task.create", {"title": "persist me", "due_date": "2026-11-05"})
        assert created["ok"] is True
        plugin.stop()

        container2 = _container_for(db_path)
        plugin2 = TaskPlugin()
        plugin2.initialize(container2)
        plugin2.start()
        try:
            listed = _dispatch(container2, "task.list", {})
            assert listed["count"] == 1
            assert listed["items"][0]["id"] == created["item_id"]
        finally:
            plugin2.stop()


class TestCreateCommand:
    def test_create_task_default_kind(self, env):
        _, container, events, _ = env
        result = _dispatch(container, "task.create", {"title": "Pay rent", "due_date": "2026-11-05"})
        assert result["ok"] is True
        assert result["item"]["kind"] == "task"
        assert result["item"]["due_date"] == "2026-11-05"
        assert result["item"]["tz"] == "Asia/Bangkok"
        assert _event_types(events) == ["task.ready", "task.created"]
        assert events[-1].type == EventType.TASK_CREATED
        assert events[-1].payload["item"]["id"] == result["item_id"]
        assert events[-1].payload["item"]["title"] == "Pay rent"

    def test_create_event_normalizes_naive_to_item_tz(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.create", {
            "kind": "event",
            "title": "Standup",
            "start_at": "2026-10-21T09:00:00",
            "end_at": "2026-10-21T09:30:00",
        })
        assert result["ok"] is True
        assert result["item"]["start_at"] == "2026-10-21T09:00:00+07:00"
        assert result["item"]["end_at"] == "2026-10-21T09:30:00+07:00"

    def test_create_event_respects_utc_tz(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.create", {
            "kind": "event",
            "title": "UTC thing",
            "start_at": "2026-10-21T09:00:00",
            "tz": "UTC",
        })
        assert result["ok"] is True
        assert result["item"]["start_at"] == "2026-10-21T09:00:00+00:00"

    def test_create_all_day_string_true(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.create", {
            "kind": "event",
            "title": "Conference",
            "start_at": "2026-10-20",
            "end_at": "2026-10-22",
            "all_day": "true",
        })
        assert result["ok"] is True
        assert result["item"]["all_day"] is True
        assert result["item"]["start_at"] == "2026-10-20"

    def test_invalid_kind_no_event_no_write(self, env):
        _, container, events, _ = env
        result = _dispatch(container, "task.create", {"kind": "bogus", "title": "x"})
        assert result["ok"] is False
        assert "invalid kind" in result["error"]
        assert _event_types(events) == ["task.ready"]
        assert container.resolve("schedule_service").list() == []

    def test_missing_title_no_event(self, env):
        _, container, events, _ = env
        result = _dispatch(container, "task.create", {"due_date": "2026-11-05"})
        assert result["ok"] is False
        assert "title" in result["error"]
        assert _event_types(events) == ["task.ready"]

    def test_event_without_start_rolls_back_no_event(self, env):
        _, container, events, _ = env
        result = _dispatch(container, "task.create", {"kind": "event", "title": "bad"})
        assert result["ok"] is False
        assert "start_at" in result["error"]
        assert _event_types(events) == ["task.ready"]
        assert container.resolve("schedule_service").list() == []

    def test_task_with_due_date_and_timed_start_allowed(self, env):
        """Phase 1 rule: due_date is separate from start_at/end_at — both may coexist."""
        _, container, _, _ = env
        result = _dispatch(container, "task.create", {
            "title": "x",
            "due_date": "2026-11-05",
            "start_at": "2026-11-04T09:00:00+07:00",
        })
        assert result["ok"] is True
        assert result["item"]["due_date"] == "2026-11-05"
        assert result["item"]["start_at"] == "2026-11-04T09:00:00+07:00"


class TestListCommand:
    def test_empty_list(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.list", {})
        assert result == {"ok": True, "count": 0, "items": []}

    def test_kind_and_status_filters(self, env):
        _, container, _, _ = env
        _dispatch(container, "task.create", {"title": "a", "due_date": "2026-11-05"})
        created = _dispatch(container, "task.create", {"kind": "event", "title": "b", "start_at": "2026-11-06T09:00:00+07:00"})
        _dispatch(container, "task.complete", {"item_id": _dispatch(container, "task.list", {"kind": "task"})["items"][0]["id"]})

        tasks = _dispatch(container, "task.list", {"kind": "task"})
        assert tasks["count"] == 1
        assert tasks["items"][0]["status"] == "completed"

        events_only = _dispatch(container, "task.list", {"kind": "event"})
        assert events_only["count"] == 1
        assert events_only["items"][0]["id"] == created["item_id"]

        pending = _dispatch(container, "task.list", {"status": "pending"})
        assert [i["id"] for i in pending["items"]] == [created["item_id"]]

    def test_invalid_kind_filter(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.list", {"kind": "bogus"})
        assert result["ok"] is False
        assert "invalid kind" in result["error"]

    def test_invalid_status_filter(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.list", {"status": "bogus"})
        assert result["ok"] is False
        assert "invalid status" in result["error"]


class TestCompleteCommand:
    def test_complete_task(self, env):
        _, container, events, _ = env
        created = _dispatch(container, "task.create", {"title": "done me", "due_date": "2026-11-05"})
        result = _dispatch(container, "task.complete", {"item_id": created["item_id"]})
        assert result["ok"] is True
        assert result["item"]["status"] == "completed"
        assert _event_types(events) == ["task.ready", "task.created", "task.completed"]
        assert events[-1].type == EventType.TASK_COMPLETED

    def test_missing_item_id(self, env):
        _, container, events, _ = env
        result = _dispatch(container, "task.complete", {})
        assert result["ok"] is False
        assert "item_id" in result["error"]
        assert _event_types(events) == ["task.ready"]

    def test_unknown_item_no_event_no_history(self, env):
        _, container, events, _ = env
        result = _dispatch(container, "task.complete", {"item_id": "item_nope"})
        assert result["ok"] is False
        assert "not found" in result["error"]
        assert _event_types(events) == ["task.ready"]
        assert _history_count(container, "item_nope") == 0

    def test_complete_twice_second_fails(self, env):
        _, container, events, _ = env
        created = _dispatch(container, "task.create", {"title": "x", "due_date": "2026-11-05"})
        assert _dispatch(container, "task.complete", {"item_id": created["item_id"]})["ok"] is True
        before = len(events)
        result = _dispatch(container, "task.complete", {"item_id": created["item_id"]})
        assert result["ok"] is False
        assert len(events) == before  # no second task.completed
        assert _history_count(container, created["item_id"]) == 2  # created + completed

    def test_complete_event_rejected(self, env):
        _, container, events, _ = env
        created = _dispatch(container, "task.create", {"kind": "event", "title": "e", "start_at": "2026-11-06T09:00:00+07:00"})
        result = _dispatch(container, "task.complete", {"item_id": created["item_id"]})
        assert result["ok"] is False
        assert "only tasks" in result["error"]
        assert _event_types(events) == ["task.ready", "task.created"]


class TestCancelCommand:
    def test_cancel_with_reason(self, env):
        _, container, events, _ = env
        created = _dispatch(container, "task.create", {"title": "x", "due_date": "2026-11-05"})
        result = _dispatch(container, "task.cancel", {"item_id": created["item_id"], "reason": "no longer needed"})
        assert result["ok"] is True
        assert result["item"]["status"] == "cancelled"
        assert events[-1].type == EventType.TASK_CANCELLED
        assert events[-1].payload["reason"] == "no longer needed"
        history = container.resolve("schedule_service").history(created["item_id"])
        assert history[0].note == "no longer needed"

    def test_cancel_event_allowed(self, env):
        _, container, _, _ = env
        created = _dispatch(container, "task.create", {"kind": "event", "title": "e", "start_at": "2026-11-06T09:00:00+07:00"})
        assert _dispatch(container, "task.cancel", {"item_id": created["item_id"]})["ok"] is True

    def test_cancel_unknown_no_event(self, env):
        _, container, events, _ = env
        result = _dispatch(container, "task.cancel", {"item_id": "item_nope"})
        assert result["ok"] is False
        assert _event_types(events) == ["task.ready"]

    def test_cancel_completed_rejected(self, env):
        _, container, events, _ = env
        created = _dispatch(container, "task.create", {"title": "x", "due_date": "2026-11-05"})
        _dispatch(container, "task.complete", {"item_id": created["item_id"]})
        before = len(events)
        result = _dispatch(container, "task.cancel", {"item_id": created["item_id"]})
        assert result["ok"] is False
        assert len(events) == before


class TestUpdateCommand:
    def test_update_title(self, env):
        _, container, events, _ = env
        created = _dispatch(container, "task.create", {"title": "old", "due_date": "2026-11-05"})
        result = _dispatch(container, "task.update", {"item_id": created["item_id"], "title": "new"})
        assert result["ok"] is True
        assert result["item"]["title"] == "new"
        assert result["changed_fields"] == ["title"]
        assert events[-1].type == EventType.TASK_UPDATED
        assert events[-1].payload["changed_fields"] == ["title"]

    def test_update_due_date(self, env):
        _, container, _, _ = env
        created = _dispatch(container, "task.create", {"title": "t", "due_date": "2026-11-05"})
        result = _dispatch(container, "task.update", {"item_id": created["item_id"], "due_date": "2026-11-07"})
        assert result["ok"] is True
        assert result["item"]["due_date"] == "2026-11-07"

    def test_update_all_day_bool_coercion(self, env):
        _, container, _, _ = env
        created = _dispatch(container, "task.create", {
            "kind": "event", "title": "e", "start_at": "2026-11-06T09:00:00+07:00",
        })
        result = _dispatch(container, "task.update", {
            "item_id": created["item_id"],
            "start_at": "2026-11-06",
            "end_at": "2026-11-06",
            "all_day": "true",
        })
        assert result["ok"] is True
        assert result["item"]["all_day"] is True
        assert result["item"]["start_at"] == "2026-11-06"
        assert "all_day" in result["changed_fields"]

    def test_update_no_fields(self, env):
        _, container, events, _ = env
        created = _dispatch(container, "task.create", {"title": "x", "due_date": "2026-11-05"})
        before = len(events)
        result = _dispatch(container, "task.update", {"item_id": created["item_id"]})
        assert result["ok"] is False
        assert "no updatable fields" in result["error"]
        assert len(events) == before

    def test_update_unknown_item(self, env):
        _, container, events, _ = env
        result = _dispatch(container, "task.update", {"item_id": "item_nope", "title": "x"})
        assert result["ok"] is False
        assert "not found" in result["error"]
        assert _event_types(events) == ["task.ready"]

    def test_update_immutable_field_rejected(self, env):
        _, container, events, _ = env
        created = _dispatch(container, "task.create", {"title": "x", "due_date": "2026-11-05"})
        before = len(events)
        result = _dispatch(container, "task.update", {"item_id": created["item_id"], "kind": "event"})
        # 'kind' is not in the handler whitelist — treated as no updatable fields
        assert result["ok"] is False
        assert len(events) == before


class TestCalendarCommand:
    def test_month_view(self, env):
        _, container, _, _ = env
        _dispatch(container, "task.create", {"title": "rent", "due_date": "2026-11-05"})
        _dispatch(container, "task.create", {
            "kind": "event", "title": "trip",
            "start_at": "2026-11-10T09:00:00+07:00",
            "end_at": "2026-11-12T12:00:00+07:00",
        })
        result = _dispatch(container, "task.calendar", {"view": "month", "year": 2026, "month": 11})
        assert result["ok"] is True
        cal = result["calendar"]
        assert cal["year"] == 2026 and cal["month"] == 11
        assert len(cal["days"]) == 30
        by_date = {d["date"]: d for d in cal["days"]}
        assert [t["title"] for t in by_date["2026-11-05"]["tasks"]] == ["rent"]
        for day in ("2026-11-10", "2026-11-11", "2026-11-12"):
            assert [e["title"] for e in by_date[day]["events"]] == ["trip"]

    def test_week_view(self, env):
        _, container, _, _ = env
        _dispatch(container, "task.create", {"title": "mon", "due_date": "2026-10-19"})
        result = _dispatch(container, "task.calendar", {"view": "week", "date": "2026-10-21"})
        assert result["ok"] is True
        cal = result["calendar"]
        assert cal["start_date"] == "2026-10-19"
        assert len(cal["days"]) == 7
        assert [t["title"] for t in cal["days"][0]["tasks"]] == ["mon"]

    def test_day_view(self, env):
        _, container, _, _ = env
        _dispatch(container, "task.create", {"title": "x", "due_date": "2026-10-20"})
        result = _dispatch(container, "task.calendar", {"view": "day", "date": "2026-10-20"})
        assert result["ok"] is True
        assert result["calendar"]["date"] == "2026-10-20"
        assert [t["title"] for t in result["calendar"]["tasks"]] == ["x"]

    def test_empty_calendar_ok(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.calendar", {"view": "month", "year": 2027, "month": 1})
        assert result["ok"] is True
        assert len(result["calendar"]["days"]) == 31
        assert all(d["events"] == [] and d["tasks"] == [] for d in result["calendar"]["days"])

    def test_invalid_view(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.calendar", {"view": "year"})
        assert result["ok"] is False
        assert "invalid view" in result["error"]

    def test_missing_date_for_day_view(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.calendar", {"view": "day"})
        assert result["ok"] is False
        assert "date" in result["error"]

    def test_malformed_date(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.calendar", {"view": "day", "date": "not-a-date"})
        assert result["ok"] is False
        assert "invalid date" in result["error"]

    def test_invalid_month(self, env):
        _, container, _, _ = env
        result = _dispatch(container, "task.calendar", {"view": "month", "year": 2026, "month": 13})
        assert result["ok"] is False


class TestSharedStateAndConfig:
    def test_uses_single_service_instance(self, env):
        """Handler path and resolved DI service must be the same object."""
        plugin, container, _, _ = env
        via_di = container.resolve("schedule_service")
        via_plugin = plugin.schedule_service
        assert via_di is via_plugin
        via_di.create(ItemKind.TASK, "via di", due_date="2026-12-01")
        listed = _dispatch(container, "task.list", {})
        assert [i["title"] for i in listed["items"]] == ["via di"]

    def test_db_path_from_config(self, env):
        _, _, _, db_path = env
        plugin_repo = env[0]._repo
        assert Path(plugin_repo._db_path) == Path(db_path)

    def test_memory_manager_not_touched(self, env, tmp_path):
        _, container, _, _ = env
        memory_path = tmp_path / "memory.db"
        memory_path.write_bytes(b"sentinel")
        _dispatch(container, "task.create", {"title": "x", "due_date": "2026-11-05"})
        assert memory_path.read_bytes() == b"sentinel"


class TestConfigFiles:
    ROOT = Path(__file__).resolve().parent.parent

    def _load(self, rel):
        with open(self.ROOT / rel, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_task_yaml_section(self):
        data = self._load("config/task.yaml")
        assert data["task"]["db_path"] == "data/tasks.db"

    def test_default_yaml_registers_plugin_and_section(self):
        data = self._load("config/default.yaml")
        mods = [(p.get("module"), p.get("class")) for p in data["plugins"]]
        assert ("aether.plugins.task_plugin", "TaskPlugin") in mods
        assert data["task"]["db_path"] == "data/tasks.db"

    def test_vision_yaml_registers_plugin(self):
        data = self._load("config/vision.yaml")
        mods = [(p.get("module"), p.get("class")) for p in data["plugins"]]
        assert ("aether.plugins.task_plugin", "TaskPlugin") in mods
