import time
import logging
from enum import Enum
from typing import Optional


class InteractionMode(Enum):
    PASSIVE = "passive"
    HOVER = "hover"
    POINTING = "pointing"
    CONFIRMING = "confirming"
    MENU_OPEN = "menu_open"


class InteractionContext:
    def __init__(self):
        self.mode = InteractionMode.PASSIVE
        self.target_object = None
        self.hand_position = None
        self.gesture = None
        self.mode_since = time.time()
        self.logger = logging.getLogger("Aether.InteractionMode")

    def transition(self, new_mode: InteractionMode):
        if self.mode != new_mode:
            self.logger.info(f"Interaction: {self.mode.value} -> {new_mode.value}")
            self.mode = new_mode
            self.mode_since = time.time()

    def update(self, gesture=None, hand_position=None):
        self.gesture = gesture
        self.hand_position = hand_position

        if gesture is None:
            if self.mode != InteractionMode.PASSIVE:
                self.transition(InteractionMode.PASSIVE)
        elif gesture == "OPEN_PALM":
            if self.mode == InteractionMode.PASSIVE:
                self.transition(InteractionMode.MENU_OPEN)
        elif gesture == "POINT":
            self.transition(InteractionMode.POINTING)
        elif gesture == "PINCH" and self.mode == InteractionMode.POINTING:
            self.transition(InteractionMode.CONFIRMING)
        elif gesture == "FIST":
            self.transition(InteractionMode.PASSIVE)

    @property
    def is_active(self):
        return self.mode != InteractionMode.PASSIVE

    @property
    def dwell_time(self):
        return (time.time() - self.mode_since) * 1000
