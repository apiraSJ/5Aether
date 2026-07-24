"""
EventBus — pure publish/subscribe messaging with sync and async support.

Per the Aether OS ADR ("EventBus is not the brain"), this bus does exactly
three things: publish, subscribe, broadcast. It never decides what a gesture
means, never opens a panel, and never stores application state.

Supports both synchronous and asynchronous handlers. Async handlers are
detected at subscribe time and scheduled via the event loop when available.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

logger = logging.getLogger("Aether.EventBus")


class EventCategory(str, Enum):
    """The four event categories the ADR reduces the system to."""

    SYSTEM = "system"
    UI = "ui"
    DATA = "data"
    COMMAND = "command"


@dataclass(frozen=True)
class Event:
    """A single message traveling through the bus."""

    name: str
    category: EventCategory
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "unknown"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=time.time)


SyncCallback = Callable[[Event], None]
AsyncCallback = Callable[[Event], Awaitable[None]]
EventCallback = Union[SyncCallback, AsyncCallback]


class EventBus:
    """Thread-safe publish/subscribe bus with sync and async handler support.

    Sync handlers are called inline. Async handlers are scheduled on the
    running event loop (if available) or called with asyncio.run() as fallback.
    """

    def __init__(self) -> None:
        self._name_subscribers: Dict[str, List[EventCallback]] = {}
        self._category_subscribers: Dict[EventCategory, List[EventCallback]] = {}
        self._lock = threading.RLock()

    def _is_async(self, callback: EventCallback) -> bool:
        return inspect.iscoroutinefunction(callback)

    def subscribe(self, name: str, callback: EventCallback) -> None:
        """Subscribe to a specific event name, e.g. 'CommandCompleted'."""
        with self._lock:
            self._name_subscribers.setdefault(name, []).append(callback)

    def subscribe_category(self, category: EventCategory, callback: EventCallback) -> None:
        """Subscribe to every event published under a whole category."""
        with self._lock:
            self._category_subscribers.setdefault(category, []).append(callback)

    def unsubscribe(self, name: str, callback: EventCallback) -> None:
        with self._lock:
            subscribers = self._name_subscribers.get(name, [])
            if callback in subscribers:
                subscribers.remove(callback)

    def unsubscribe_category(self, category: EventCategory, callback: EventCallback) -> None:
        with self._lock:
            subscribers = self._category_subscribers.get(category, [])
            if callback in subscribers:
                subscribers.remove(callback)

    def publish(self, event: Event) -> None:
        """Deliver an event to every matching subscriber.

        Sync handlers are called inline. Async handlers are scheduled.
        A misbehaving subscriber is logged and skipped.
        """
        with self._lock:
            name_subs = list(self._name_subscribers.get(event.name, []))
            category_subs = list(self._category_subscribers.get(event.category, []))

        for callback in name_subs + category_subs:
            if self._is_async(callback):
                self._schedule_async(callback, event)
            else:
                try:
                    callback(event)
                except Exception:
                    logger.exception(
                        "Sync subscriber '%s' raised while handling event '%s'",
                        getattr(callback, "__name__", repr(callback)),
                        event.name,
                    )

    def publish_simple(
        self,
        name: str,
        category: EventCategory = EventCategory.SYSTEM,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "system",
    ) -> Event:
        """Convenience wrapper: build an Event and publish it in one call."""
        event = Event(name=name, category=category, payload=payload or {}, source=source)
        self.publish(event)
        return event

    def _schedule_async(self, callback: AsyncCallback, event: Event) -> None:
        """Schedule an async callback on the current event loop, or run as fallback."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._safe_async_call(callback, event))
        except RuntimeError:
            # No running loop (sync context). Run in a new loop.
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(self._safe_async_call(callback, event))
                finally:
                    loop.close()
            except Exception:
                logger.exception(
                    "Failed to run async subscriber '%s'",
                    getattr(callback, "__name__", repr(callback)),
                )

    @staticmethod
    async def _safe_async_call(callback: AsyncCallback, event: Event) -> None:
        try:
            await callback(event)
        except Exception:
            logger.exception(
                "Async subscriber '%s' raised while handling event '%s'",
                getattr(callback, "__name__", repr(callback)),
                event.name,
            )
