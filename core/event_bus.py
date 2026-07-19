import logging
from enum import Enum
from typing import Callable, Any
from collections import defaultdict
import threading
import time


class EventType(Enum):
    OBJECT_DETECTED = "object_detected"
    OBJECT_TRACKED = "object_tracked"
    OBJECT_LOST = "object_lost"
    OBJECT_HELD = "object_held"
    HAND_DETECTED = "hand_detected"
    HAND_LOST = "hand_lost"
    GESTURE_RECOGNIZED = "gesture_recognized"
    GESTURE_STABLE = "gesture_stable"
    GESTURE_LOST = "gesture_lost"
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_COMPLETED = "task_completed"
    TASK_CANCELLED = "task_cancelled"
    COMMAND_EXECUTED = "command_executed"
    COMMAND_FAILED = "command_failed"
    PLUGIN_STARTED = "plugin_started"
    PLUGIN_STOPPED = "plugin_stopped"
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    LOG_ENTRY = "log_entry"


class Event:
    def __init__(self, event_type: EventType, data: dict = None, source: str = ""):
        self.event_type = event_type
        self.data = data or {}
        self.source = source
        self.timestamp = time.time()
        self.id = f"{event_type.value}_{int(self.timestamp * 1000)}"

    def __repr__(self):
        return f"Event({self.event_type.value}, source={self.source})"


class EventBus:
    def __init__(self):
        self._subscribers = defaultdict(list)
        self._lock = threading.Lock()
        self._history = []
        self._max_history = 1000
        self.logger = logging.getLogger("Aether.EventBus")

    def emit(self, event_type: EventType, data: dict = None, source: str = ""):
        event = Event(event_type, data, source)

        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)

        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                self.logger.error(f"Handler error for {event_type.value}: {e}")

    def subscribe(self, event_type: EventType, handler: Callable):
        with self._lock:
            self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: Callable):
        with self._lock:
            if handler in self._subscribers[event_type]:
                self._subscribers[event_type].remove(handler)

    def get_history(self, event_type: EventType = None, limit: int = 50):
        with self._lock:
            if event_type:
                events = [e for e in self._history if e.event_type == event_type]
            else:
                events = list(self._history)
            return events[-limit:]

    def clear_history(self):
        with self._lock:
            self._history.clear()

    def subscriber_count(self, event_type: EventType = None):
        with self._lock:
            if event_type:
                return len(self._subscribers.get(event_type, []))
            return sum(len(handlers) for handlers in self._subscribers.values())
