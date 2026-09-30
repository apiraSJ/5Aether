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
from typing import Any, Union

from aether.core.event_type import EventType
from aether.core.profiler import profiler

logger = logging.getLogger("Aether.EventBusV2")


@dataclass(slots=True)
class Event:
    """Immutable event payload.

    Attributes:
        type:       The event type (unified EventType enum).
        payload:    Event-specific data dictionary.
        source:     Identifier of the component that emitted this event.
        timestamp:  Unix timestamp of event creation.
    """

    type: Union[EventType, str]
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: float = field(default_factory=lambda: __import__("time").time)


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

        # Metrics: per-event-type cumulative + 1-second window rates
        self._stats: dict[str, dict] = defaultdict(
            lambda: {"published": 0, "delivered": 0, "orphans": 0}
        )
        self._published_total: int = 0
        self._delivered_total: int = 0
        self._orphan_total: int = 0
        self._window_published: int = 0
        self._window_delivered: int = 0
        self._window_orphans: int = 0
        self._window_start: float = __import__("time").perf_counter()
        self._events_per_sec: float = 0.0
        self._delivered_per_sec: float = 0.0
        self._orphans_per_sec: float = 0.0

    # --- Configuration ---

    @property
    def is_queued(self) -> bool:
        return self._queued

    def set_queued(self, queued: bool) -> None:
        """Switch mode at runtime (e.g., during migration)."""
        with self._lock:
            self._queued = queued

    # --- Subscribe / Unsubscribe ---

    def subscribe(self, event_type: Union[EventType, str], callback: Callable[[Event], None]) -> None:
        """Register callback for event_type. Thread-safe.

        event_type can be EventType enum or string for backward compatibility.
        """
        # Normalize to string for internal storage
        key = event_type.value if isinstance(event_type, EventType) else event_type
        with self._lock:
            if callback not in self._subscribers[key]:
                self._subscribers[key].append(callback)
                logger.debug("Subscribed %s to %s", callback.__qualname__, key)

    def unsubscribe(self, event_type: Union[EventType, str], callback: Callable[[Event], None]) -> None:
        """Remove callback. Thread-safe."""
        key = event_type.value if isinstance(event_type, EventType) else event_type
        with self._lock:
            if callback in self._subscribers[key]:
                self._subscribers[key].remove(callback)
                logger.debug("Unsubscribed %s from %s", callback.__qualname__, key)

    # --- Publish ---

    def _event_key(self, event_type: Union[EventType, str]) -> str:
        return event_type.value if isinstance(event_type, EventType) else event_type

    def _count_published(self, event_type: Union[EventType, str]) -> None:
        key = self._event_key(event_type)
        self._stats[key]["published"] += 1
        self._published_total += 1
        self._window_published += 1

    def publish(self, event: Event) -> None:
        """Emit event. Behavior depends on mode:
        - queued=True:  append to internal queue, deliver on flush()
        - queued=False: deliver immediately to all subscribers (legacy)
        """
        if not isinstance(event, Event):
            raise TypeError(f"Expected Event, got {type(event).__name__}")

        if self._queued:
            with self._lock:
                event.timestamp = __import__("time").perf_counter()
                self._count_published(event.type)
                self._queue.append(event)
        else:
            self._count_published(event.type)
            self._deliver(event)

    def publish_now(self, event_type: Union[EventType, str], payload: dict[str, Any] = None, source: str = "") -> None:
        """Convenience: create and publish immediately (bypasses queue even in queued mode).
        Use sparingly — only for system-critical events that must not wait.
        """
        self._count_published(event_type)
        self._deliver(Event(type=event_type, payload=payload or {}, source=source))

    # --- Flush (called once per Application tick) ---

    def _update_window_rates(self, now: float) -> None:
        """Roll the 1-second window rates. Caller must hold the lock."""
        elapsed = now - self._window_start
        if elapsed >= 1.0:
            self._events_per_sec = self._window_published / elapsed
            self._delivered_per_sec = self._window_delivered / elapsed
            self._orphans_per_sec = self._window_orphans / elapsed
            self._window_published = 0
            self._window_delivered = 0
            self._window_orphans = 0
            self._window_start = now

    def _report_queue(self, depth: int, flush_ms: float, oldest_ms: float) -> None:
        """Push event bus metrics to the profiler."""
        profiler.set_queue(
            "eventbus",
            queued=depth,
            flush_ms=flush_ms,
            oldest_ms=oldest_ms,
            events_per_sec=round(self._events_per_sec, 1),
            delivered_per_sec=round(self._delivered_per_sec, 1),
            orphans_per_sec=round(self._orphans_per_sec, 1),
            total_published=self._published_total,
            total_delivered=self._delivered_total,
            total_orphans=self._orphan_total,
        )

    def flush(self) -> int:
        """Deliver all queued events to subscribers. Returns count delivered.
        Call exactly once per tick from Application.tick().
        """
        t0 = __import__("time").perf_counter()

        with self._lock:
            now = __import__("time").perf_counter()

            if not self._queue:
                self._update_window_rates(now)
                self._report_queue(depth=0, flush_ms=0.0, oldest_ms=0.0)
                return 0

            # Compute oldest event age
            oldest_ms = (now - self._queue[0].timestamp) * 1000.0

            events = self._queue[:]
            self._queue.clear()

        delivered = 0
        for event in events:
            self._deliver(event)
            delivered += 1

        ms = (__import__("time").perf_counter() - t0) * 1000.0
        with self._lock:
            # Roll rates after delivery so this flush's deliveries/orphans
            # are included in the window that just closed.
            self._update_window_rates(__import__("time").perf_counter())
            self._report_queue(depth=len(self._queue), flush_ms=ms, oldest_ms=oldest_ms)
        profiler._record_stage("eventbus_flush", ms)

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
        # Normalize event type to string for subscriber lookup
        event_key = self._event_key(event.type)

        # Snapshot subscribers under lock to avoid holding lock during callbacks
        with self._lock:
            subscribers = list(self._subscribers.get(event_key, []))
            if subscribers:
                self._stats[event_key]["delivered"] += len(subscribers)
                self._delivered_total += len(subscribers)
                self._window_delivered += len(subscribers)
            else:
                # Orphan event: published but nobody subscribed at delivery time
                self._stats[event_key]["orphans"] += 1
                self._orphan_total += 1
                self._window_orphans += 1

        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                logger.exception("Subscriber %s raised for event %s", callback.__qualname__, event_key)

    # --- Debug / Introspection ---

    def get_subscriber_count(self, event_type: Union[EventType, str]) -> int:
        key = self._event_key(event_type)
        with self._lock:
            return len(self._subscribers.get(key, []))

    def get_all_event_types(self) -> list[str]:
        with self._lock:
            return list(self._subscribers.keys())

    def get_event_stats(self) -> dict[str, dict]:
        """Per-event-type counters: published / delivered / orphans (cumulative)."""
        with self._lock:
            return {k: dict(v) for k, v in self._stats.items()}

    def get_orphan_event_types(self) -> list[str]:
        """Event types that were published with zero subscribers at delivery."""
        with self._lock:
            return [k for k, v in self._stats.items() if v["orphans"] > 0]

    def get_totals(self) -> dict:
        """Cumulative published / delivered / orphan counts across all types."""
        with self._lock:
            return {
                "published": self._published_total,
                "delivered": self._delivered_total,
                "orphans": self._orphan_total,
            }