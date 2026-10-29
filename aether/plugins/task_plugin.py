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
task.update, task.calendar, task.export, task.import. Handlers return
plain dicts and translate ScheduleError into {"ok": False, "error": ...}
with no event and no history (the service rolls the transaction back
atomically).
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from aether.core.command import Command
from aether.core.command_registry import CommandInfo, CommandRegistry
from aether.core.event_bus import Event, EventCategory
from aether.core.event_type import EventType
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer
from aether.task import calendar_query, json_adapter
from aether.task.calendar_query import day_view, month_view, views_to_dicts, week_view
from aether.task import extraction
from aether.task.contextcal import ContextCalService
from aether.task.drafts import DraftStore
from aether.task.models import DEFAULT_TZ, InternalStatus, ItemKind, ItemStatus, ReviewState, item_to_dict
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
    CommandInfo(
        name="task.export",
        description="Export items to a provider-neutral JSON file",
        category="task",
        params_help="[path] [kind=<task|event>]",
        examples=("task.export path=data/backup.json", "task.export"),
    ),
    CommandInfo(
        name="task.import",
        description="Import items from a JSON file (validated first, atomic)",
        category="task",
        params_help="<path> [on_conflict=review|update|skip]",
        examples=("task.import path=data/backup.json", "task.import path=data/backup.json on_conflict=update"),
    ),
    CommandInfo(
        name="task.extract",
        description="Extract schedule items from free text (deterministic)",
        category="task",
        params_help="text=<...>",
    ),
    CommandInfo(
        name="task.review.list",
        description="List review queue",
        category="task",
        params_help="[state=pending|confirmed|rejected|edited]",
    ),
    CommandInfo(
        name="task.review.confirm",
        description="Confirm a pending review",
        category="task",
        params_help="<review_id>",
    ),
    CommandInfo(
        name="task.review.edit",
        description="Edit and confirm a pending review",
        category="task",
        params_help="<review_id> [title] [due_date] [start_at] [end_at] [all_day] [owner] [description] [tz]",
    ),
    CommandInfo(
        name="task.review.reject",
        description="Reject a pending review (deletes item)",
        category="task",
        params_help="<review_id>",
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
        self._drafts: Optional[DraftStore] = None
        self._contextcal: Optional[ContextCalService] = None
        self._db_path: str = "data/tasks.db"

    @property
    def schedule_service(self) -> Optional[ScheduleService]:
        """The shared ScheduleService instance (single write path)."""
        return self._service

    @property
    def contextcal_service(self) -> Optional[ContextCalService]:
        """The shared ContextCalService instance."""
        return self._contextcal

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
        self._drafts = DraftStore()
        self._contextcal = ContextCalService(self._service, self._drafts, repository=self._repo)

        self._register_commands()

        container.register_instance("schedule_repository", self._repo)
        container.register_instance("schedule_service", self._service)
        container.register_instance("contextcal_service", self._contextcal)
        container.register_instance("calendar_query", calendar_query)

        logger.info("TaskPlugin initialized (db: %s)", self._db_path)

    def start(self) -> None:
        if self._repo:
            self._repo.open()
        if self._event_bus:
            try:
                self._event_bus.publish(Event(
                    name=EventType.TASK_READY.value,
                    category=EventCategory.DATA,
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
            self._command_bus.register_handler("task.export", self._handle_export)
            self._command_bus.register_handler("task.import", self._handle_import)
            self._command_bus.register_handler("task.extract", self._handle_extract)
            self._command_bus.register_handler("task.review.list", self._handle_review_list)
            self._command_bus.register_handler("task.review.confirm", self._handle_review_confirm)
            self._command_bus.register_handler("task.review.edit", self._handle_review_edit)
            self._command_bus.register_handler("task.review.reject", self._handle_review_reject)

    # ── Publish helpers (post-commit only) ─────────────────────────

    def _publish(self, event_type: EventType, payload: Dict[str, Any]) -> None:
        if not self._event_bus:
            return
        try:
            self._event_bus.publish(Event(name=event_type.value, category=EventCategory.DATA, payload=payload, source=self.name))
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

    def _handle_export(self, command: Command) -> dict:
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

        path = _opt(p.get("path")) or "data/tasks-export.json"
        items = self._service.list(kind=kind)
        try:
            written = json_adapter.export_to_file(items, path)
        except OSError as e:
            return {"ok": False, "error": f"cannot write {path}: {e}"}

        return {
            "ok": True,
            "path": written,
            "count": len(items),
            "message": f"Exported {len(items)} item(s) to {written}",
        }

    def _handle_import(self, command: Command) -> dict:
        if not self._service or not self._repo:
            return {"ok": False, "error": "task system not initialized"}
        p = command.params

        path = _opt(p.get("path"))
        if not path:
            return {"ok": False, "error": "path is required"}

        on_conflict = (_opt(p.get("on_conflict")) or "review").lower()
        if on_conflict not in ("review", "update", "skip"):
            return {
                "ok": False,
                "error": f"invalid on_conflict: {on_conflict!r} (use review|update|skip)",
            }

        target = Path(path)
        try:
            data = json_adapter.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"ok": False, "error": f"file not found: {path}"}
        except UnicodeDecodeError:
            return {"ok": False, "error": f"not a UTF-8 text file: {path}"}
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"invalid JSON in {path}: {e}"}
        except OSError as e:
            return {"ok": False, "error": f"cannot read {path}: {e}"}

        try:
            result = json_adapter.import_data(
                self._service,
                self._repo,
                data,
                on_conflict=on_conflict,
                actor=str(command.source or "import"),
            )
        except json_adapter.ImportFormatError as e:
            return {
                "ok": False,
                "error": f"validation failed — nothing imported ({len(e.errors)} problem(s))",
                "errors": e.errors,
            }
        except ScheduleError as e:
            # Domain failure inside the transaction: rolled back wholesale.
            return {"ok": False, "error": f"import failed and was rolled back: {e}"}

        return result.as_dict()

    def _handle_extract(self, command: Command) -> dict:
        if not self._service or not self._repo:
            return {"ok": False, "error": "task system not initialized"}
        p = command.params
        text = _opt(p.get("text")) or ""
        if not text:
            return {"ok": False, "error": "text is required"}
        candidates = extraction.extract(text)
        created = []
        needs_confirmation = []
        try:
            with self._repo.transaction():
                import time, hashlib
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                # Check dedup
                existing = self._repo.find_batch_by_hash(content_hash)
                if existing is not None:
                    return {"ok": True, "deduplicated": True, "batch_id": existing.id, "created": 0, "needs_confirmation": 0}
                batch_id = f"imp_{hashlib.sha256((text+str(time.time())).encode('utf-8')).hexdigest()[:12]}"
                stats = {"created": 0, "needs_confirmation": 0}
                for cand in candidates:
                    if cand.needs_review:
                        item = self._service.create(
                            cand.kind,
                            cand.title,
                            description=cand.description,
                            due_date=cand.due_date,
                            start_at=cand.start_at,
                            end_at=cand.end_at,
                            all_day=cand.all_day,
                            tz=cand.tz or DEFAULT_TZ,
                            source="extraction",
                            internal_status=InternalStatus.NEEDS_CONFIRMATION,
                            actor=str(command.source or "extract"),
                        )
                        from aether.task.models import ReviewEntry, ReviewState
                        review = ReviewEntry(
                            item_id=item.id,
                            reason=cand.review_reason or "needs confirmation",
                            payload={**cand.review_payload, "kind": "extraction"},
                            confidence=cand.confidence,
                            state=ReviewState.PENDING,
                        )
                        self._repo.enqueue_review(review)
                        self._service.attach_evidence(item.id, source="chat", source_ref="extraction", excerpt=cand.raw_excerpt or text, confidence=cand.confidence)
                        needs_confirmation.append({"item_id": item.id, "review_id": review.id})
                        stats["needs_confirmation"] += 1
                    else:
                        item = self._service.create(
                            cand.kind,
                            cand.title,
                            description=cand.description,
                            due_date=cand.due_date,
                            start_at=cand.start_at,
                            end_at=cand.end_at,
                            all_day=cand.all_day,
                            tz=cand.tz or DEFAULT_TZ,
                            source="extraction",
                            actor=str(command.source or "extract"),
                        )
                        self._service.attach_evidence(item.id, source="chat", source_ref="extraction", excerpt=cand.raw_excerpt or text, confidence=cand.confidence)
                        created.append({"item_id": item.id})
                        stats["created"] += 1
                from aether.task.models import ImportBatch
                batch = ImportBatch(
                    id=batch_id,
                    source="extraction",
                    format_version="1",
                    content_hash=content_hash,
                    item_count=len(candidates),
                    stats=stats,
                )
                self._repo.record_batch(batch)
        except Exception as e:
            return {"ok": False, "error": f"extraction failed and was rolled back: {e}"}
        return {"ok": True, "created": created, "needs_confirmation": needs_confirmation, "count": len(candidates)}

    def _handle_review_list(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}
        p = command.params
        state = None
        state_text = _opt(p.get("state"))
        if state_text:
            try:
                state = ReviewState(state_text.lower())
            except ValueError:
                return {"ok": False, "error": f"invalid state: {state_text!r}"}
        reviews = self._service.list_reviews(state) if state is not None else self._service.list_pending_reviews()
        return {"ok": True, "reviews": [{"id": r.id, "item_id": r.item_id, "reason": r.reason, "payload": r.payload, "confidence": r.confidence, "state": r.state.value} for r in reviews]}

    def _handle_review_confirm(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}
        review_id = _opt(command.params.get("review_id")) or _opt(command.params.get("id"))
        if not review_id:
            return {"ok": False, "error": "review_id is required"}
        try:
            res = self._service.resolve_review(review_id, "confirm", actor=str(command.source or "user"))
            return res
        except ScheduleError as e:
            return {"ok": False, "error": str(e)}

    def _handle_review_edit(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}
        review_id = _opt(command.params.get("review_id")) or _opt(command.params.get("id"))
        if not review_id:
            return {"ok": False, "error": "review_id is required"}
        p = command.params
        corrected = {}
        for field in _UPDATE_PARAM_FIELDS:
            if field in p:
                value = _opt(p.get(field))
                if value is not None:
                    corrected[field] = value
        if "all_day" in p:
            corrected["all_day"] = _as_bool(p.get("all_day"))
        try:
            res = self._service.resolve_review(review_id, "edit", corrected_fields=corrected, actor=str(command.source or "user"))
            return res
        except ScheduleError as e:
            return {"ok": False, "error": str(e)}

    def _handle_review_reject(self, command: Command) -> dict:
        if not self._service:
            return {"ok": False, "error": "task system not initialized"}
        review_id = _opt(command.params.get("review_id")) or _opt(command.params.get("id"))
        if not review_id:
            return {"ok": False, "error": "review_id is required"}
        try:
            res = self._service.resolve_review(review_id, "reject", actor=str(command.source or "user"))
            return res
        except ScheduleError as e:
            return {"ok": False, "error": str(e)}
