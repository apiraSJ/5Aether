import time
import logging
import math
from enum import Enum
from typing import Optional, List
from dataclasses import dataclass

from vision.hand_tracker import HandData, HandResults


class GestureType(Enum):
    OPEN_PALM = "open_palm"
    POINT = "point"
    PINCH = "pinch"
    FIST = "fist"
    PEACE = "peace"
    THUMBS_UP = "thumbs_up"
    UNKNOWN = "unknown"


@dataclass
class GestureEvent:
    gesture: GestureType
    hand: HandData
    position: tuple
    confidence: float
    timestamp_ms: int


class GestureEngine:
    def __init__(self, config: dict = None):
        self.logger = logging.getLogger("Aether.GestureEngine")
        self.config = config or {}
        self.stability_threshold = self.config.get("movement_stability_px", 8)
        self.dwell_time_ms = self.config.get("dwell_time_ms", 500)
        self._prev_hand_center = None
        self._stable_since = 0
        self._is_stable = False

    def update(self, hand_results: HandResults, interaction_active: bool = True) -> List[GestureEvent]:
        if not hand_results or not hand_results.hands:
            self._prev_hand_center = None
            self._is_stable = False
            return []

        events = []
        for hand in hand_results.hands:
            center = self._get_hand_center(hand)

            is_stable = self._check_stability(center, hand_results.timestamp_ms)

            if interaction_active and is_stable:
                gesture = self._recognize(hand)
                if gesture != GestureType.UNKNOWN:
                    events.append(GestureEvent(
                        gesture=gesture,
                        hand=hand,
                        position=center,
                        confidence=hand.confidence,
                        timestamp_ms=hand_results.timestamp_ms,
                    ))

            self._prev_hand_center = center

        return events

    def _check_stability(self, center: tuple, timestamp_ms: int) -> bool:
        if self._prev_hand_center is None:
            self._stable_since = timestamp_ms
            self._is_stable = False
            return False

        dx = center[0] - self._prev_hand_center[0]
        dy = center[1] - self._prev_hand_center[1]
        movement = math.sqrt(dx * dx + dy * dy)

        if movement < self.stability_threshold:
            if not self._is_stable:
                self._stable_since = timestamp_ms
            elapsed = timestamp_ms - self._stable_since
            self._is_stable = elapsed >= self.dwell_time_ms
        else:
            self._is_stable = False
            self._stable_since = timestamp_ms

        return self._is_stable

    def _recognize(self, hand: HandData) -> GestureType:
        if not hand.landmarks or len(hand.landmarks) < 21:
            return GestureType.UNKNOWN

        lm = hand.landmarks
        fingers_extended = self._count_extended_fingers(lm)

        thumb_tip = lm[4]
        index_tip = lm[8]
        pinch_dist = math.sqrt(
            (thumb_tip.x - index_tip.x) ** 2 +
            (thumb_tip.y - index_tip.y) ** 2
        )

        if pinch_dist < 0.04:
            return GestureType.PINCH

        if fingers_extended >= 4:
            return GestureType.OPEN_PALM

        if fingers_extended == 1 and self._is_index_extended(lm):
            return GestureType.POINT

        if fingers_extended == 2 and self._is_index_middle_extended(lm):
            return GestureType.PEACE

        if fingers_extended == 0 and self._is_thumb_extended(lm):
            return GestureType.THUMBS_UP

        if fingers_extended == 0:
            return GestureType.FIST

        return GestureType.UNKNOWN

    def _count_extended_fingers(self, landmarks) -> int:
        count = 0
        if self._is_thumb_extended(landmarks):
            count += 1
        if self._is_index_extended(landmarks):
            count += 1
        if self._is_middle_extended(landmarks):
            count += 1
        if self._is_ring_extended(landmarks):
            count += 1
        if self._is_pinky_extended(landmarks):
            count += 1
        return count

    def _is_thumb_extended(self, lm) -> bool:
        return lm[4].x < lm[3].x if lm[4].x < lm[2].x else lm[4].x > lm[3].x

    def _is_index_extended(self, lm) -> bool:
        return lm[8].y < lm[6].y

    def _is_middle_extended(self, lm) -> bool:
        return lm[12].y < lm[10].y

    def _is_ring_extended(self, lm) -> bool:
        return lm[16].y < lm[14].y

    def _is_pinky_extended(self, lm) -> bool:
        return lm[20].y < lm[18].y

    def _is_index_middle_extended(self, lm) -> bool:
        return self._is_index_extended(lm) and self._is_middle_extended(lm)

    def _get_hand_center(self, hand: HandData) -> tuple:
        wrist = hand.landmarks[0]
        middle_mcp = hand.landmarks[9]
        cx = (wrist.x + middle_mcp.x) / 2
        cy = (wrist.y + middle_mcp.y) / 2
        return (cx, cy)
