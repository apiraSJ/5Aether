"""
FrameBroker — Thread-safe frame distribution with per-consumer events

Producers call update_frame(); each consumer registers via register_consumer()
and receives its own private threading.Event. When a new frame arrives,
ALL consumer events are set. Each consumer clears only its own event.
"""

import threading


class FrameBroker:
    """Thread-safe reference storage for raw incoming camera matrices.

    Each consumer gets its own Event — no more shared-event race condition.
    """

    def __init__(self):
        self._current_frame = None
        self._lock = threading.Lock()
        self._consumers: dict[str, threading.Event] = {}
        self._counter = 0

    def update_frame(self, frame):
        with self._lock:
            self._current_frame = frame.copy()
            for event in self._consumers.values():
                event.set()

    def get_frame(self):
        with self._lock:
            return self._current_frame.copy() if self._current_frame is not None else None

    def register_consumer(self, name: str = None) -> threading.Event:
        event = threading.Event()
        with self._lock:
            if name is None:
                name = f"consumer_{self._counter}"
                self._counter += 1
            self._consumers[name] = event
        return event

    def unregister_consumer(self, name: str):
        with self._lock:
            self._consumers.pop(name, None)

    @property
    def new_frame_event(self):
        with self._lock:
            if "_legacy" not in self._consumers:
                self._consumers["_legacy"] = threading.Event()
            return self._consumers["_legacy"]

    def clear_event(self):
        with self._lock:
            if "_legacy" in self._consumers:
                self._consumers["_legacy"].clear()
