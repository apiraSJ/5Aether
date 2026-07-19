import time
import logging
from dataclasses import dataclass
from typing import Optional

from vision.gesture_engine import GestureType


@dataclass
class PendingAction:
    action: str
    target: object
    preview_until: float


@dataclass
class Action:
    type: str
    action: str = None
    target: object = None


class CommandConfirmation:
    def __init__(self, config: dict = None):
        self.logger = logging.getLogger("Aether.CommandConfirmation")
        self.config = config or {}
        self.preview_timeout_ms = self.config.get("preview_timeout_ms", 3000)
        self.pending_action: Optional[PendingAction] = None

    def handle_gesture(self, gesture_event, context=None) -> list:
        actions = []
        now = time.time()

        if self.pending_action and now > self.pending_action.preview_until:
            self.pending_action = None

        if gesture_event.gesture == GestureType.POINT:
            target = self._find_target_at(gesture_event.position, context)
            if target:
                self.pending_action = PendingAction(
                    action="select_object",
                    target=target,
                    preview_until=now + (self.preview_timeout_ms / 1000.0),
                )
                actions.append(Action(type="PREVIEW", target=target))

        elif gesture_event.gesture == GestureType.PINCH and self.pending_action:
            action = self.pending_action
            self.pending_action = None
            actions.append(Action(type="EXECUTE", action=action.action, target=action.target))

        elif gesture_event.gesture == GestureType.FIST:
            self.pending_action = None
            actions.append(Action(type="CANCEL"))

        return actions

    def _find_target_at(self, position: tuple, context=None):
        if context and hasattr(context, 'find_object_at'):
            return context.find_object_at(position)
        return None

    def cancel(self):
        self.pending_action = None

    @property
    def has_pending(self):
        return self.pending_action is not None
