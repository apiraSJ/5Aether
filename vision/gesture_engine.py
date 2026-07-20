"""
Simple Gesture Engine — 5 Core Gestures

Detects gestures from 21 hand landmarks using finger counting.
No model dependency — just math on tip vs joint positions.
"""

import time
import logging
import math
from typing import Optional, List
from dataclasses import dataclass

from vision.hand_tracker import HandData, HandResults
from vision.gesture_actions import GestureType, HandFeatures, GestureAction, ActionType


@dataclass
class GestureEvent:
    gesture: GestureType
    hand: HandData
    position: tuple
    confidence: float = 0.0
    timestamp_ms: int = 0


class GestureEngine:
    def __init__(self, config: dict = None):
        self.logger = logging.getLogger("Aether.GestureEngine")
        self.config = config or {}

        self._last_gesture: Optional[GestureType] = None
        self._cursor_x = 0.5
        self._cursor_y = 0.5

    def update(self, hand_results: HandResults, interaction_active: bool = True) -> List[GestureEvent]:
        if not hand_results or not hand_results.hands:
            self._last_gesture = None
            return []

        events = []
        for hand in hand_results.hands:
            if not hand.landmarks or len(hand.landmarks) < 21:
                continue

            lm = hand.landmarks

            if HandFeatures.is_finger_extended(lm, "index") and not HandFeatures.is_finger_extended(lm, "middle"):
                self._cursor_x, self._cursor_y = HandFeatures.index_tip_position(lm)

            if interaction_active:
                gesture = self._recognize(lm)

                if gesture != GestureType.UNKNOWN and gesture != self._last_gesture:
                    center = HandFeatures.hand_center(lm)
                    events.append(GestureEvent(
                        gesture=gesture,
                        hand=hand,
                        position=center,
                        confidence=hand.confidence,
                        timestamp_ms=hand_results.timestamp_ms,
                    ))
                self._last_gesture = gesture

        return events

    def _recognize(self, lm) -> GestureType:
        """Simple finger-counting gesture recognition.

        Closed_Fist:  0 fingers open
        Pointing_Up:  only index open
        Thumb_Up:     only thumb open, tip above MCP
        Thumb_Down:   only thumb open, tip below MCP
        Open_Palm:    4+ fingers open
        """
        ext = HandFeatures.count_extended(lm)
        thumb_up = HandFeatures.is_finger_extended(lm, "thumb")
        index_up = HandFeatures.is_finger_extended(lm, "index")

        if ext == 0:
            return GestureType.FIST

        if ext == 1 and thumb_up and not index_up:
            tip = lm[4]
            mcp = lm[2]
            return GestureType.THUMBS_UP if tip.y < mcp.y else GestureType.THUMB_DOWN

        if ext == 1 and index_up and not thumb_up:
            return GestureType.POINT

        if ext >= 4:
            return GestureType.OPEN_PALM

        return GestureType.UNKNOWN

    def get_cursor_position(self) -> tuple:
        return (self._cursor_x, self._cursor_y)
