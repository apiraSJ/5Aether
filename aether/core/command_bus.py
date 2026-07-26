"""CommandBus — command dispatch with queued execution for the tick loop.

Commands are dispatched by plugins, queued, and processed during Application.tick().
This ensures deterministic ordering and keeps plugins non-blocking.

Emits lifecycle events on EventBus:
  command.issued   — when dispatch() is called
  command.started  — when execution begins
  command.completed — on success
  command.failed   — on failure
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, List, Optional

from aether.core.command import Command
from aether.core.command_result import CommandResult
from aether.core.result_pipeline import ResultPipeline
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.CommandBus")


@dataclass
class QueuedCommand:
    """Command wrapper for the dispatch queue."""

    command: Command
    handler: Optional[Callable] = None
    timeout: float = 30.0
    future: Optional[Any] = None  # for async support later
    enqueued_at: float = field(default_factory=time.time)


class CommandBus:
    """Dispatch Command objects with queued execution per tick.

    Plugins call dispatch() which enqueues. Application.tick() calls update()
    which processes the queue in FIFO order.
    """

    def __init__(
        self,
        result_pipeline: Optional[ResultPipeline] = None,
        container: Optional[ServiceContainer] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        self._container = container
        self._result_pipeline = result_pipeline
        self._event_bus = event_bus

        # Handler registry: command_name -> handler callable
        self._handlers: Dict[str, Callable] = {}

        # Execution queue
        self._queue: Deque[QueuedCommand] = deque()
        self._queue_lock = threading.Lock()

        # History for status queries
        self._history: Dict[str, Command] = {}
        self._history_lock = threading.Lock()

        # Statistics
        self._processed_count = 0
        self._failed_count = 0

    # --- Handler registration ---

    def register_handler(self, command_name: str, handler: Callable) -> None:
        """Register a handler for a command name.

        Handler signature: handler(command: Command) -> Any
        """
        with self._queue_lock:
            if command_name in self._handlers:
                logger.warning("Overriding handler for command: %s", command_name)
            self._handlers[command_name] = handler
            logger.debug("Registered handler for command: %s", command_name)

    def unregister_handler(self, command_name: str) -> None:
        with self._queue_lock:
            self._handlers.pop(command_name, None)

    def is_registered(self, command_name: str) -> bool:
        return command_name in self._handlers

    # --- Dispatch (called by plugins) ---

    def dispatch(
        self,
        command: Command,
        handler: Optional[Callable] = None,
        timeout: float = 30.0,
    ) -> None:
        """Enqueue a command for execution on the next tick.

        Non-blocking. Returns immediately. Use get_status() to check result.
        """
        if handler is None:
            handler = self._handlers.get(command.name)

        queued = QueuedCommand(command=command, handler=handler, timeout=timeout)

        with self._queue_lock:
            self._queue.append(queued)

        command.status = "QUEUED"
        self._emit("command.issued", command)
        logger.debug("Enqueued command: %s (queue depth: %d)", command.name, len(self._queue))

    def dispatch_sync(
        self,
        command: Command,
        handler: Optional[Callable] = None,
        timeout: float = 30.0,
    ) -> Any:
        """Execute command immediately (bypasses queue).

        Use sparingly — for boot-time commands only.
        """
        if handler is None:
            handler = self._handlers.get(command.name)

        return self._execute(command, handler, timeout)

    # --- Tick processing (called by Application.tick) ---

    def update(self) -> int:
        """Process all queued commands. Returns count processed."""
        processed = 0

        while True:
            with self._queue_lock:
                if not self._queue:
                    break
                queued = self._queue.popleft()

            try:
                self._execute(queued.command, queued.handler, queued.timeout)
                processed += 1
                self._processed_count += 1
            except Exception:
                self._failed_count += 1
                # Exception already logged in _execute
                # Continue processing remaining commands

        return processed

    def _execute(
        self,
        command: Command,
        handler: Optional[Callable],
        timeout: float,
    ) -> Any:
        """Execute a single command with its handler."""
        start = time.time()
        command.status = "EXECUTING"
        self._emit("command.started", command)

        # Store in history
        with self._history_lock:
            self._history[command.id] = command

        try:
            if handler:
                result = self._execute_with_timeout(handler, command, timeout, start)
                command.result = result
                command.status = "COMPLETED"
                duration_ms = (time.time() - start) * 1000
                logger.debug("Command %s completed in %.1fms", command.name, duration_ms)

                self._emit("command.completed", command, {"duration_ms": duration_ms})

                # Publish success via ResultPipeline
                if self._result_pipeline:
                    cmd_result = CommandResult.ok(
                        command_id=command.id,
                        command_name=command.name,
                        message=f"Command {command.name} completed",
                        data={"result": result},
                        notification="toast",
                    )
                    cmd_result.duration_ms = duration_ms
                    self._result_pipeline.publish(cmd_result)

                return result
            else:
                command.status = "COMPLETED"
                command.error = "No handler registered"
                logger.warning("No handler for command: %s", command.name)
                self._emit("command.completed", command)
                if self._result_pipeline:
                    cmd_result = CommandResult.ok(
                        command_id=command.id,
                        command_name=command.name,
                        message="No handler registered",
                    )
                    self._result_pipeline.publish(cmd_result)
                return command

        except Exception as e:
            command.status = "FAILED"
            command.error = str(e)
            duration_ms = (time.time() - start) * 1000
            logger.exception("Command %s failed: %s", command.name, e)

            self._emit("command.failed", command, {"duration_ms": duration_ms, "error": str(e)})

            if self._result_pipeline:
                cmd_result = CommandResult.fail(
                    command_id=command.id,
                    command_name=command.name,
                    error=str(e),
                    notification="toast",
                )
                cmd_result.duration_ms = duration_ms
                self._result_pipeline.publish(cmd_result)
            raise

    def _execute_with_timeout(
        self, handler: Callable, command: Command, timeout: float, start_time: float
    ) -> Any:
        """Execute handler with timeout protection in a worker thread."""
        result_holder: List[Any] = []
        exception_holder: List[Exception] = []

        def target() -> None:
            try:
                result_holder.append(handler(command))
            except Exception as e:
                exception_holder.append(e)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout)

        if thread.is_alive():
            raise TimeoutError(f"Command {command.name} timed out after {timeout}s")

        if exception_holder:
            raise exception_holder[0]

        return result_holder[0] if result_holder else None

    # --- Status / History ---

    def get_status(self, command_id: str) -> Optional[Command]:
        with self._history_lock:
            return self._history.get(command_id)

    def get_recent(self, limit: int = 50) -> List[Command]:
        with self._history_lock:
            return list(self._history.values())[-limit:]

    def clear_history(self, max_age: float = 3600.0) -> int:
        """Remove old completed/failed commands. Returns count removed."""
        now = time.time()
        removed = 0
        with self._history_lock:
            to_remove = [
                cid for cid, cmd in self._history.items()
                if (now - cmd.created_at) > max_age and cmd.status in ("COMPLETED", "FAILED")
            ]
            for cid in to_remove:
                del self._history[cid]
            removed = len(to_remove)

        if removed:
            logger.debug("Cleared %d old commands from history", removed)
        return removed

    # --- Properties ---

    @property
    def queue_depth(self) -> int:
        with self._queue_lock:
            return len(self._queue)

    @property
    def processed_count(self) -> int:
        return self._processed_count

    @property
    def failed_count(self) -> int:
        return self._failed_count

    @property
    def result_pipeline(self) -> Optional[ResultPipeline]:
        return self._result_pipeline

    @result_pipeline.setter
    def result_pipeline(self, value: ResultPipeline) -> None:
        self._result_pipeline = value

    # --- Event emission ---

    def _emit(self, event_type: str, command: Command, extra: dict = None) -> None:
        """Emit a lifecycle event on the EventBus if available."""
        if self._event_bus is None:
            return
        from aether.core.event_bus_v2 import Event

        payload = {
            "command": command.name,
            "command_id": command.id,
            "source": command.source,
            "status": command.status,
            "params": command.params,
        }
        if command.result is not None:
            payload["result"] = command.result
        if command.error is not None:
            payload["error"] = command.error
        if extra:
            payload.update(extra)

        self._event_bus.publish(Event(type=event_type, payload=payload, source="command_bus"))