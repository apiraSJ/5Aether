"""ResultPipeline — low-level result broker that publishes Command results.

Plugins subscribe to handlers for successful/failed execution and status updates.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from aether.core.command import Command

logger = logging.getLogger("Aether.ResultPipeline")


@dataclass
class CommandResult:
    """Represents the result of command execution."""

    command: Command
    type: str = "status"  # status, complete, error, info
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: __import__("time").time())


class ResultPipeline:
    """Handles command result publishing and result handler management."""

    def __init__(self, event_bus=None) -> None:
        self._handlers: Dict[str, List[Callable]] = {
            "status": [],
            "complete": [],
            "error": [],
            "info": [],
        }
        self._lock = threading.RLock()
        self.logger = logging.getLogger("Aether.ResultPipeline")
        self._event_bus = event_bus

    def add_handler(self, type_name: str, handler: Callable) -> None:
        """Add a handler for result type."""
        with self._lock:
            if type_name not in self._handlers:
                raise ValueError(
                    f"Unknown result type: {type_name}. Must be one of: {list(self._handlers.keys())}"
                )
            self._handlers[type_name].append(handler)
            self.logger.debug(f"Added {type_name} handler: {handler.__name__}")

    def publish(self, command: Command, result_type: str, data: Dict[str, Any]) -> None:
        """Publish a command result of given type."""
        if result_type not in self._handlers:
            logger.warning(f"Unknown result_type '{result_type}', default to 'info'")
            result_type = "info"

        result = CommandResult(command, result_type, data)

        with self._lock:
            handlers = self._handlers[result_type].copy()

        self.logger.debug(
            f"Publishing {result_type} for command '{command.name}' (ID: {command.id})"
        )

        for handler in handlers:
            try:
                handler(result)
            except Exception as e:
                logger.error(
                    f"Result handler {handler.__name__} failed: {e}",
                    exc_info=True,
                )

    def get_handlers(self, type_name: str) -> List[Callable]:
        """Get all handlers of a given type."""
        with self._lock:
            return self._handlers.get(type_name, []).copy()

    def get_all_handlers(self) -> Dict[str, List[Callable]]:
        """Get all registered handlers of all types."""
        with self._lock:
            return {k: v.copy() for k, v in self._handlers.items()}