"""
Gesture Action Executor — Simple bridge from gesture to action.

Processes gesture events and emits them on the EventBus.
"""

import logging
import time
from typing import Optional, List
from dataclasses import dataclass

from vision.gesture_engine import GestureEngine, GestureEvent
from vision.gesture_actions import (
    GestureType, ActionType, GestureAction, DEFAULT_GESTURE_MAP
)
from core.event_bus import EventBus, EventType


@dataclass
class GestureActionState:
    last_gesture: Optional[GestureType] = None
    last_action_time: float = 0.0
    cursor_x: float = 0.5
    cursor_y: float = 0.5
    cooldown_ms: int = 800


class GestureActionExecutor:
    def __init__(self, event_bus: EventBus, gesture_engine: GestureEngine):
        self.logger = logging.getLogger("Aether.GestureExecutor")
        self.event_bus = event_bus
        self.gesture_engine = gesture_engine
        self._state = GestureActionState()

    def process_events(self, events: List[GestureEvent]) -> List[GestureAction]:
        actions = []
        now = time.time() * 1000

        for event in events:
            if (event.gesture == self._state.last_gesture and
                    now - self._state.last_action_time < self._state.cooldown_ms):
                continue

            action_type = DEFAULT_GESTURE_MAP.get(event.gesture, ActionType.NO_ACTION)
            if action_type == ActionType.NO_ACTION:
                continue

            action = GestureAction(
                action=action_type,
                gesture=event.gesture,
                position=event.position,
                confidence=event.confidence,
                timestamp_ms=event.timestamp_ms,
            )

            self.event_bus.emit(EventType.GESTURE_RECOGNIZED, data={
                "gesture": event.gesture.value,
                "action": action_type.value,
                "position": list(event.position),
                "confidence": event.confidence,
            }, source="gesture_executor")

            actions.append(action)
            self._state.last_gesture = event.gesture
            self._state.last_action_time = now

        cx, cy = self.gesture_engine.get_cursor_position()
        self._state.cursor_x = cx
        self._state.cursor_y = cy

        return actions

    def get_cursor(self) -> tuple:
        return (self._state.cursor_x, self._state.cursor_y)
