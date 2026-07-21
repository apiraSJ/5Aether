from typing import Callable, Any, Dict, List
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import logging


class EventType(Enum):
    """Core event types in Aether."""
    # System
    SYSTEM_START = "system_start"
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_ERROR = "system_error"
    
    # UI
    UI_OPEN = "ui_open"
    UI_CLOSE = "ui_close"
    UI_OPEN_REQUESTED = "ui_open_requested"
    UI_CLOSE_REQUESTED = "ui_close_requested"
    UI_PANEL_SWITCH = "ui_panel_switch"
    UI_UPDATE = "ui_update"
    PANEL_SHOW_REQUESTED = "panel_show_requested"
    PANEL_HIDE_REQUESTED = "panel_hide_requested"
    MODE_CHANGED = "mode_changed"
    
    # Input
    INPUT_KEYBOARD = "input_keyboard"
    INPUT_MOUSE = "input_mouse"
    INPUT_HOTKEY = "input_hotkey"
    
    # Command
    COMMAND_EXECUTE = "command_execute"
    COMMAND_COMPLETE = "command_complete"
    COMMAND_FAILED = "command_failed"
    
    # Tasks
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    TASK_COMPLETED = "task_completed"
    TASK_CANCELLED = "task_cancelled"
    
    # Plugins
    PLUGIN_STARTED = "plugin_started"
    PLUGIN_STOPPED = "plugin_stopped"
    
    # Vision
    HAND_DETECTED = "hand_detected"
    HAND_LOST = "hand_lost"
    OBJECT_DETECTED = "object_detected"
    OBJECT_TRACKED = "object_tracked"
    OBJECT_LOST = "object_lost"
    GESTURE_RECOGNIZED = "gesture_recognized"
    GESTURE_STABLE = "gesture_stable"
    GESTURE_LOST = "gesture_lost"
    HELP_REQUESTED = "help_requested"
    
    # Context
    CONTEXT_CHANGED = "context_changed"
    CONTEXT_APP_CHANGED = "context_app_changed"
    
    # Memory
    MEMORY_STORE = "memory_store"
    MEMORY_RECALL = "memory_recall"
    
    # Menu
    MENU_OPEN = "menu_open"
    MENU_CLOSE = "menu_close"
    MENU_ITEM_SELECTED = "menu_item_selected"

    # Status
    STATUS_REQUESTED = "status_requested"


@dataclass
class Event:
    """Event data structure."""
    type: EventType
    data: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: f"{time.time()}_{id(object())}")


class EventBus:
    """Central event bus - the nervous system of Aether.
    
    All inputs (keyboard, gesture, voice) become events.
    All modules communicate through events.
    """
    
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = {}
        self._lock = threading.Lock()
        self._history: List[Event] = []
        self._max_history = 1000
        self.logger = logging.getLogger("Aether.EventBus")
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Subscribe to an event type."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)
        self.logger.debug(f"Subscribed {handler.__name__} to {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        """Unsubscribe from an event type."""
        with self._lock:
            if event_type in self._subscribers:
                try:
                    self._subscribers[event_type].remove(handler)
                except ValueError:
                    pass
    
    def emit(self, event_or_type, data: dict = None, source: str = "", **kwargs) -> None:
        """Emit an event. Accepts an Event object, or (EventType, data=, source=)."""
        if isinstance(event_or_type, Event):
            event = event_or_type
        else:
            event = Event(type=event_or_type, data=data or {}, source=source)

        # Store in history
        with self._lock:
            self._history.append(event)
            if len(self._history) > self._max_history:
                self._history.pop(0)
            
            handlers = self._subscribers.get(event.type, []).copy()
        
        # Execute handlers
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                self.logger.error(f"Handler error for {event.type.value}: {e}")
    
    def emit_simple(self, event_type: EventType, data: Dict[str, Any] = None, source: str = "") -> None:
        """Convenience method to emit a simple event."""
        self.emit(Event(type=event_type, data=data or {}, source=source))
    
    def get_history(self, event_type: EventType = None, limit: int = 50) -> List[Event]:
        """Get event history."""
        with self._lock:
            if event_type:
                return [e for e in self._history if e.type == event_type][-limit:]
            return self._history[-limit:]
    
    def subscriber_count(self, event_type: EventType = None) -> int:
        """Count subscribers for a given event type, or total if None."""
        with self._lock:
            if event_type:
                return len(self._subscribers.get(event_type, []))
            return sum(len(handlers) for handlers in self._subscribers.values())


# Global event bus instance
_global_bus: EventBus = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance."""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


def set_event_bus(bus: EventBus) -> None:
    """Set the global event bus instance."""
    global _global_bus
    _global_bus = bus