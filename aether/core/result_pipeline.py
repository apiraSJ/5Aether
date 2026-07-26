"""ResultPipeline — low-level result broker that publishes Command results.

Plugins subscribe to handlers for successful/failed execution and status updates.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List

from aether.core.command import Command
from aether.core.command_result import CommandResult

logger = logging.getLogger("Aether.ResultPipeline")


class ResultPipeline:
    """Handles command result publishing and result handler management.

    The ResultPipeline fans out CommandResults to:
    - NotificationHandler (toast, banner, popup, modal)
    - HistoryHandler (command history, undo tracking)
    - LayoutHandler (focus panels, update UI)
    - EventBus (lifecycle events)
    """

    def __init__(self, event_bus: Any = None) -> None:
        self._handlers: Dict[str, List[Callable[[CommandResult], None]]] = {
            "success": [],
            "error": [],
            "notification": [],
            "history": [],
            "layout": [],
        }
        self._lock = threading.RLock()
        self.logger = logging.getLogger("Aether.ResultPipeline")
        self._event_bus = event_bus

    def add_handler(self, type_name: str, handler: Callable[[CommandResult], None]) -> None:
        """Add a handler for result type.

        type_name must be one of: success, error, notification, history, layout
        """
        with self._lock:
            if type_name not in self._handlers:
                raise ValueError(
                    f"Unknown result type: {type_name}. Must be one of: {list(self._handlers.keys())}"
                )
            self._handlers[type_name].append(handler)
            self.logger.debug(f"Added {type_name} handler: {handler.__name__}")

    def publish(self, result: CommandResult) -> None:
        """Publish a CommandResult to all registered handlers.

        This is the main entry point - handlers are called based on the result's properties:
        - success/error handlers based on result.success
        - notification handlers if result.notification is set
        - history handlers if result.history is True
        - layout handlers if result.layout_action is set
        """
        # Determine which handler groups to notify
        handler_groups: List[str] = []

        if result.success:
            handler_groups.append("success")
        else:
            handler_groups.append("error")

        if result.notification:
            handler_groups.append("notification")

        if result.history:
            handler_groups.append("history")

        if result.layout_action:
            handler_groups.append("layout")

        # Collect handlers
        handlers_to_call: List[Callable[[CommandResult], None]] = []
        with self._lock:
            for group in handler_groups:
                handlers_to_call.extend(self._handlers.get(group, []))

        self.logger.debug(
            f"Publishing result for command '{result.command_name}' "
            f"(success={result.success}, groups={handler_groups})"
        )

        # Call all handlers
        for handler in handlers_to_call:
            try:
                handler(result)
            except Exception as e:
                logger.error(
                    f"Result handler {handler.__name__} failed: {e}",
                    exc_info=True,
                )

    def get_handlers(self, type_name: str) -> List[Callable[[CommandResult], None]]:
        """Get all handlers of a given type."""
        with self._lock:
            return self._handlers.get(type_name, []).copy()

    def get_all_handlers(self) -> Dict[str, List[Callable[[CommandResult], None]]]:
        """Get all registered handlers of all types."""
        with self._lock:
            return {k: v.copy() for k, v in self._handlers.items()}