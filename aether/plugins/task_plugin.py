"""TaskPlugin — lifecycle and Command/Event integration for Mark 1 tasks.

Architecture:
    TaskPlugin.initialize()
        → Creates SqliteScheduleRepository + ScheduleService (data/tasks.db,
          separate from memory.db — locked Mark 1 decision)
        → Registers task.* commands in CommandRegistry + handlers on CommandBus
        → Registers schedule_repository / schedule_service / calendar_query
          in the DI container (single shared instances)

    TaskPlugin.start()
        → Opens the database connection
        → Publishes task.ready

    TaskPlugin.stop()
        → Closes the database connection

Events published (AFTER the ScheduleService transaction commits — the
service commits before returning, so publishing on success is publish
after commit by construction; failures raise ScheduleError before any
write and publish nothing):
    task.ready       — repo opened, system available (boot)
    task.created     — payload {"item": item_to_dict(...)}
    task.updated     — payload {"item": ..., "changed_fields": [str]}
    task.completed   — payload {"item": ...}
    task.cancelled   — payload {"item": ..., "reason": str|None}

Commands: task.create, task.list, task.complete, task.cancel,
task.update, task.calendar. Handlers return plain dicts and translate
ScheduleError into {"ok": False, "error": ...} with no event and no
history (the service rolls the transaction back atomically).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, Optional

from aether.core.command import Command
from aether.core.command_registry import CommandInfo, CommandRegistry
from aether.core.event_bus_v2 import Event
from aether.core.event_type import EventType
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer
from aether.task import calendar_query
from aether.task.calendar_query import day_view, month_view, views_to_dicts, week_view
from aether.task.models import DEFAULT_TZ, ItemKind, ItemStatus, item_to_dict
from aether.task.repository import SqliteScheduleRepository
from aether.task.service import ScheduleError, ScheduleService

logger = logging.getLogger("Aether.TaskPlugin")

_TASK_COMMANDS = [
    CommandInfo(
        name="task.create",
        description="Create a task or event",
        category="task",
        params_help="kind=<task|event> title=<text> [due_date] [start_at] [end_at] [all_day] [owner] [tz]",
        examples=(
            "task.create title='Pay rent' due_date=2026-11-05",
            "task.create kind=event title='Standup' start_at=2026-10-21T09:00:00+07:00",
        ),
    ),
    CommandInfo(
        name="task.list",
        description="List tasks and events",
        category="task",
        params_help="[kind=<task|event>] [status=<pending|completed|cancelled>]",
    ),
    CommandInfo(
        name="task.complete",
        description="Mark an item completed",
        category="task",
        params_help="<item_id>",
    ),
    CommandInfo(
        name="task.cancel",
        description="Cancel an item (reason kept in history)",
        category="task",
        params_help="<item_id> [reason]",
    ),
    CommandInfo(
        name="task.update",
        description="Update fields of an item",
        category="task",
        params_help="<item_id> [title] [due_date] [start_at] [end_at] [all_day] [owner] [description] [tz]",
    ),
    CommandInfo(
        name="task.calendar",
        description="Calendar views (day/week/month) over stored items",
        category="task",
        params_help="view=<day|week|month> date=<YYYY-MM-DD>  |  view=month year=YYYY month=M",
        examples=("task.calendar view=month year=2026 month=10", "task.calendar view=day date=2026-10-21"),
    ),
]

_UPDATE_PARAM_FIELDS = ("title", "description", "due_date", "start_at", "end_at", "owner", "tz", "source")


def _opt(value: Any) -> Optional[str]:
    """Normalize a command param to a stripped string or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "y", "on"):
        return True
    if text in ("false", "0", "no", "n", "off", "", "none"):
        return False
    return bool(value)


class TaskPlugin(PluginBase):
    """Manages Mark 1 schedule items (tasks + events) and calendar views."""

    name = "task_plugin"

    def __init__(self) -> None:
        self._container: Optional[ServiceContainer] = None
        self._event_bus = None
        self._command_bus = None
        self._repo: Optional[SqliteScheduleRepository] = None
        self._service: Optional[ScheduleService] = None
        self._db_path: str = "data/tasks.db"

    @property
    def schedule_service(self) -> Optional[ScheduleService]:
        """The shared ScheduleService instance (single write path)."""
        return self._service

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Task & Calendar",
            version="1.0",
            category="task",
            commands=[c.name for c in _TASK_COMMANDS],
            description="Mark 1 task/calendar assistant: CRUD, calendar views, TASK_* events",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._event_bus = container.resolve("event_bus")
        self._command_bus = container.resolve("command_bus")

        if container.has("config"):
            config = container.resolve("config")
            self._db_path = config.get("task.db_path", "data/tasks.db")

        self._repo = SqliteScheduleRepository(self._db_path)
        self._service = ScheduleService(self._repo)

        self._register_commands()

        container.register_instance("schedule_repository", self._repo)
        container.register_instance("schedule_service", self._service)
        container.register_instance("calendar_query", calendar_query)

        logger.info("TaskPlugin initialized (db: %s)", self._db_path)

    def start(self) -> None:
        if self._repo:
            self._repo.open()
        if self._event_bus:
            try:
                self._event_bus.publish(Event(
                    type=EventType.TASK_READY,
                    payload={
                        "db_path": self._db_path,
                        "items": self._repo.count() if self._repo else 0,
                    },
                    source=self.name,
                ))
            except Exception as e:
                logger.warning("Failed to publish task.ready: %s", e)
        logger.info("TaskPlugin started")

    def is_ready(self) -> bool:
        """True when the schedule repository exists and its database is open."""
        return self._repo is not None and self._repo.is_open

    def stop(self) -> None:
        if self._repo:
            self._repo.close()
        logger.info("TaskPlugin stopped")

    # ── Command registration ───────────────────────────────────────

    def _register_commands(self) -> None:
        if not self._container:
            return

        if self._container.has("command_registry"):
            registry = self._container.resolve("command_registry")
        else:
            registry = CommandRegistry()
            registry.initialize(self._container)

        for cmd_info in _TASK_COMMANDS:
            registry.register(cmd_info)

        if self._command_bus:
            self._command_bus.register_handler("task.create", self._handle_create)
            self._command_bus.register_handler("task.list", self._handle_list)
            self._command_bus.register_handler("task.complete", self._handle_complete)
            self._command_bus.register_handler("task.cancel", self._handle_cancel)
            self._command_bus.register_handler("task.update", self._handle_update)
            self._command_bus.register_handler("task.calendar", self._handle_calendar)

    # ── Publish helpers (post-commit only) ─────────────────────────

    def _publish(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        if not self._event_bus:
            return
        try:
            self._event_bus.publish(Event(type=event_type, payload=payload, source=self.name))
        except Exception as e:
            logger.warning("Failed to publish %s: %s", event_type, e)

    # ── Command handlers ───────────────────────────────────────────

    def _handle_create(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}
        p = command.params

        kind_text = _opt(p.get("kind")) or "task"
        try:
            kind = ItemKind(kind_text.lower())
        except ValueError:
            return {"ok": False, "error": f"invalid kind: {kind_text!r} (use 'task' or 'event')"}

        title = _opt(p.get("title"))
        if not title:
            return {"ok": False, "error": "title is required"}

        all_day = _as_bool(p.get("all_day", False))
        tz = _opt(p.get("tz")) or DEFAULT_TZ

        try:
            item = self._service.create(
                kind,
                title,
                description=_opt(p.get("description")) or "",
                due_date=_opt(p.get("due_date")),
                start_at=_opt(p.get("start_at")),
                end_at=_opt(p.get("end_at")),
                all_day=all_day,
                tz=tz,
                owner=_opt(p.get("owner")),
                source=_opt(p.get("source")) or "manual",
                actor=str(command.source or "user"),
            )
        except ScheduleError as e:
            return {"ok": False, "error": str(e)}

        self._publish(EventType.TASK_CREATED, {"item": item_to_dict(item)})
        return {
            "ok": True,
            "item_id": item.id,
            "item": item_to_dict(item),
            "message": f"Created {item.kind.value} '{item.title}' ({item.id})",
        }

    def _handle_list(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}
        p = command.params

        kind = None
        kind_text = _opt(p.get("kind"))
        if kind_text:
            try:
                kind = ItemKind(kind_text.lower())
            except ValueError:
                return {"ok": False, "error": f"invalid kind: {kind_text!r} (use 'task' or 'event')"}

        status = None
        status_text = _opt(p.get("status"))
        if status_text:
            try:
                status = ItemStatus(status_text.lower())
            except ValueError:
                return {
                    "ok": False,
                    "error": f"invalid status: {status_text!r} (use pending|completed|cancelled)",
                }

        items = self._service.list(kind=kind, status=status)
        return {
            "ok": True,
            "count": len(items),
            "items": [item_to_dict(i) for i in items],
        }

    def _handle_complete(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}

        item_id = _opt(command.params.get("item_id"))
        if not item_id:
            return {"ok": False, "error": "item_id is required"}

        try:
            item = self._service.complete(item_id, actor=str(command.source or "user"))
        except ScheduleError as e:
            return {"ok": False, "error": str(e)}

        self._publish(EventType.TASK_COMPLETED, {"item": item_to_dict(item)})
        return {
            "ok": True,
            "item_id": item.id,
            "item": item_to_dict(item),
            "message": f"Completed '{item.title}' ({item.id})",
        }

    def _handle_cancel(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}
        p = command.params

        item_id = _opt(p.get("item_id"))
        if not item_id:
            return {"ok": False, "error": "item_id is required"}

        reason = _opt(p.get("reason"))
        try:
            item = self._service.cancel(
                item_id, actor=str(command.source or "user"), reason=reason or ""
            )
        except ScheduleError as e:
            return {"ok": False, "error": str(e)}

        self._publish(EventType.TASK_CANCELLED, {"item": item_to_dict(item), "reason": reason})
        return {
            "ok": True,
            "item_id": item.id,
            "item": item_to_dict(item),
            "message": f"Cancelled '{item.title}' ({item.id})",
        }

    def _handle_update(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}
        p = command.params

        item_id = _opt(p.get("item_id"))
        if not item_id:
            return {"ok": False, "error": "item_id is required"}

        changes: Dict[str, Any] = {}
        for field in _UPDATE_PARAM_FIELDS:
            if field in p:
                value = _opt(p.get(field))
                if value is not None:
                    changes[field] = value
        if "all_day" in p:
            changes["all_day"] = _as_bool(p.get("all_day"))

        if not changes:
            return {
                "ok": False,
                "error": "no updatable fields given (title, due_date, start_at, end_at, all_day, owner, description, tz)",
            }

        expected = p.get("expected_updated_at")
        expected_updated_at = float(expected) if expected is not None else None

        try:
            item = self._service.update(
                item_id,
                expected_updated_at=expected_updated_at,
                actor=str(command.source or "user"),
                **changes,
            )
        except ScheduleError as e:
            return {"ok": False, "error": str(e)}

        self._publish(EventType.TASK_UPDATED, {
            "item": item_to_dict(item),
            "changed_fields": sorted(changes.keys()),
        })
        return {
            "ok": True,
            "item_id": item.id,
            "item": item_to_dict(item),
            "changed_fields": sorted(changes.keys()),
            "message": f"Updated '{item.title}' ({item.id}): {', '.join(sorted(changes.keys()))}",
        }

    def _handle_calendar(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}
        p = command.params

        view = (_opt(p.get("view")) or "month").lower()
        if view not in ("day", "week", "month"):
            return {"ok": False, "error": f"invalid view: {view!r} (use day|week|month)"}

        items = self._service.list()

        try:
            if view in ("day", "week"):
                day = _opt(p.get("date"))
                if not day:
                    return {"ok": False, "error": "date=<YYYY-MM-DD> is required for day/week view"}
                date.fromisoformat(day)
                result = day_view(items, day) if view == "day" else week_view(items, day)
            else:
                year = int(p.get("year", 0))
                month = int(p.get("month", 0))
                date(year, month, 1)
                result = month_view(items, year, month)
        except (ValueError, TypeError) as e:
            return {"ok": False, "error": f"invalid date parameters: {e}"}

        return {
            "ok": True,
            "view": view,
            "calendar": views_to_dicts(result),
        }
