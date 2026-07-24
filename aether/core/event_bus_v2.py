"""EventBus v2 — queued, deterministic, per-tick flush.

Phase B: dual-mode (queued=True by default, queued=False for legacy compat).
Phase C: queued-only.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("Aether.EventBusV2")


@dataclass(slots=True)
class Event:
    """Immutable event payload."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""


class EventBus:
    """Thread-safe publish/subscribe with optional queued delivery.

    Modes:
      - queued=True  (default Phase B): publish() enqueues, flush() delivers per tick
      - queued=False (legacy compat):   publish() delivers immediately

    Deterministic ordering: FIFO within each tick, subscribers called in registration order.
    """

    def __init__(self, queued: bool = True) -> None:
        self._queued = queued
        self._subscribers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._queue: list[Event] = []
        self._lock = threading.RLock()
        self._delivering = False

    # --- Configuration ---

    @property
    def is_queued(self) -> bool:
        return self._queued

    def set_queued(self, queued: bool) -> None:
        """Switch mode at runtime (e.g., during migration)."""
        with self._lock:
            self._queued = queued

    # --- Subscribe / Unsubscribe ---

    def subscribe(self, event_type: str, callback: Callable[[Event], None]) -> None:
        """Register callback for event_type. Thread-safe."""
        with self._lock:
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)
                logger.debug("Subscribed %s to %s", callback.__qualname__, event_type)

    def unsubscribe(self, event_type: str, callback: Callable[[Event], None]) -> None:
        """Remove callback. Thread-safe."""
        with self._lock:
            if callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)
                logger.debug("Unsubscribed %s from %s", callback.__qualname__, event_type)

    # --- Publish ---

    def publish(self, event: Event) -> None:
        """Emit event. Behavior depends on mode:
        - queued=True:  append to internal queue, deliver on flush()
        - queued=False: deliver immediately to all subscribers (legacy)
        """
        if not isinstance(event, Event):
            raise TypeError(f"Expected Event, got {type(event).__name__}")

        if self._queued:
            with self._lock:
                self._queue.append(event)
        else:
            self._deliver(event)

    def publish_now(self, event_type: str, payload: dict[str, Any] = None, source: str = "") -> None:
        """Convenience: create and publish immediately (bypasses queue even in queued mode).
        Use sparingly — only for system-critical events that must not wait.
        """
        self._deliver(Event(type=event_type, payload=payload or {}, source=source))

    # --- Flush (called once per Application tick) ---

    def flush(self) -> int:
        """Deliver all queued events to subscribers. Returns count delivered.
        Call exactly once per tick from Application.tick().
        """
        with self._lock:
            if not self._queue:
                return 0
            events = self._queue[:]
            self._queue.clear()

        delivered = 0
        for event in events:
            self._deliver(event)
            delivered += 1

        logger.debug("Flushed %d events", delivered)
        return delivered

    def queue_size(self) -> int:
        """Number of events waiting for next flush."""
        with self._lock:
            return len(self._queue)

    def clear_queue(self) -> int:
        """Discard queued events. Returns count discarded."""
        with self._lock:
            n = len(self._queue)
            self._queue.clear()
            return n

    # --- Internal delivery ---

    def _deliver(self, event: Event) -> None:
        """Call all subscribers for event.type. Exceptions logged, not propagated."""
        # Snapshot subscribers under lock to avoid holding lock during callbacks
        with self._lock:
            subscribers = list(self._subscribers.get(event.type, []))

        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                logger.exception("Subscriber %s raised for event %s", callback.__qualname__, event.type)

    # --- Debug / Introspection ---

    def get_subscriber_count(self, event_type: str) -> int:
        with self._lock:
            return len(self._subscribers.get(event_type, []))

    def get_all_event_types(self) -> list[str]:
        with self._lock:
            return list(self._subscribers.keys())