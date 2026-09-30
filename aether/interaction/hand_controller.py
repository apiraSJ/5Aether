"""HandController — converts MediaPipe hand output into HandInputEvents.

This is a pure input adapter. It does NOT know about panels, memory,
windows, or layouts. It only produces HandInputEvents that are routed
through InputRouter → InteractionController → CommandBus/EventBus.

Architecture:
    MediaPipe Hand Landmarks → HandController → InputRouter → InteractionController

Rules:
    - HandController NEVER calls UI directly
    - HandController NEVER modifies panel state
    - HandController ONLY produces HandInputEvents
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Callable

from aether.interaction.gestures import Gesture

logger = logging.getLogger("Aether.HandController")


class HandGesture(Enum):
    """Recognized hand gestures. Deprecated — use Gesture enum instead.

    Kept for backward compatibility in HandInputEvent.gesture field.
    Will be replaced by Gesture enum in a future release.
    """
    NONE = auto()
    OPEN_PALM = auto()
    FIST = auto()
    PINCH = auto()
    THUMB_UP = auto()
    PEACE = auto()
    POINT_UP = auto()
    SWIPE_LEFT = auto()
    SWIPE_RIGHT = auto()
    SWIPE_UP = auto()
    SWIPE_DOWN = auto()


def _hand_gesture_to_gesture(hg: HandGesture) -> Gesture:
    """Map legacy HandGesture to canonical Gesture enum."""
    mapping = {
        HandGesture.NONE: Gesture.NONE,
        HandGesture.OPEN_PALM: Gesture.OPEN_PALM,
        HandGesture.FIST: Gesture.CLOSED_FIST,
        HandGesture.PINCH: Gesture.PINCH,
        HandGesture.THUMB_UP: Gesture.THUMB_UP,
        HandGesture.PEACE: Gesture.PEACE,
        HandGesture.POINT_UP: Gesture.POINT_UP,
        HandGesture.SWIPE_LEFT: Gesture.SWIPE_LEFT,
        HandGesture.SWIPE_RIGHT: Gesture.SWIPE_RIGHT,
        HandGesture.SWIPE_UP: Gesture.SWIPE_UP,
        HandGesture.SWIPE_DOWN: Gesture.SWIPE_DOWN,
    }
    return mapping.get(hg, Gesture.NONE)


@dataclass
class HandInputEvent:
    """Input event produced by HandController.

    This is the ONLY output of HandController.
    Routed through InputRouter → InteractionController.

    Fields:
        position_x/y: Normalized [0,1] or screen pixels
        gesture: HandGesture enum (legacy, kept for backward compat)
        gesture_enum: Canonical Gesture enum (preferred for new code)
        confidence: Gesture classification confidence
        timestamp: Event timestamp
        hand_label: "Left" or "Right"
    """
    position_x: float = 0.0       # Normalized [0,1] or screen pixels
    position_y: float = 0.0
    gesture: HandGesture = HandGesture.NONE
    confidence: float = 0.0
    timestamp: float = 0.0
    hand_label: str = ""          # "Left" or "Right"

    @property
    def gesture_enum(self) -> Gesture:
        """Canonical Gesture enum. Preferred for new code."""
        return _hand_gesture_to_gesture(self.gesture)

    @property
    def is_valid(self) -> bool:
        return self.confidence > 0.0 and self.gesture != HandGesture.NONE


class HandController:
    """Converts MediaPipe hand landmarks into HandInputEvents.

    This is a pure input adapter — no business logic.
    Produces HandInputEvents that flow through InputRouter.

    HandController does NOT know about:
        - Panels
        - Memory
        - Windows
        - Layouts
        - Any UI concepts

    It ONLY produces:
        - HandInputEvent with position, gesture, confidence
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        self._config = config or {}
        self._enabled = self._config.get("enabled", True)
        self._preferred_hand = self._config.get("preferred_hand", "right")
        self._confidence_threshold = self._config.get("global_confidence_threshold", 0.5)
        self._last_event: Optional[HandInputEvent] = None
        self._gesture_cooldowns: dict[str, float] = {}
        self._gesture_configs: dict[str, dict] = {}

    def load_gesture_config(self, gesture_configs: dict) -> None:
        """Load gesture-to-command mappings from config.

        Args:
            gesture_configs: Dict of gesture_name → {command, cooldown, confidence, ...}
        """
        self._gesture_configs = gesture_configs
        logger.info("Loaded %d gesture configs", len(gesture_configs))

    def process_hand_landmarks(
        self,
        landmarks: list[dict],
        gesture_name: str,
        confidence: float,
        hand_label: str = "Right",
        timestamp: Optional[float] = None,
    ) -> Optional[HandInputEvent]:
        """Process MediaPipe hand landmarks into a HandInputEvent.

        Args:
            landmarks: MediaPipe hand landmarks (21 points)
            gesture_name: Classified gesture name from MediaPipe
            confidence: Gesture classification confidence
            hand_label: "Left" or "Right"
            timestamp: Optional timestamp, uses current time if None

        Returns:
            HandInputEvent if valid, None if filtered out.
        """
        if not self._enabled:
            return None

        if not landmarks or len(landmarks) < 21:
            return None

        # Filter by preferred hand
        if self._preferred_hand != "both" and hand_label.lower() != self._preferred_hand.lower():
            return None

        ts = timestamp or time.perf_counter()

        # Extract index fingertip position (landmark 8)
        index_tip = landmarks[8]
        position_x = index_tip.get("x", 0.5)
        position_y = index_tip.get("y", 0.5)

        # Map gesture name to enum
        gesture = self._map_gesture(gesture_name)

        # Apply confidence threshold
        if confidence < self._confidence_threshold:
            gesture = HandGesture.NONE

        # Check cooldown
        if not self._check_cooldown(gesture_name, ts):
            gesture = HandGesture.NONE

        event = HandInputEvent(
            position_x=position_x,
            position_y=position_y,
            gesture=gesture,
            confidence=confidence,
            timestamp=ts,
            hand_label=hand_label,
        )

        self._last_event = event
        return event

    def process_pinch_position(
        self,
        thumb_x: float,
        thumb_y: float,
        index_x: float,
        index_y: float,
        confidence: float,
        hand_label: str = "Right",
        timestamp: Optional[float] = None,
    ) -> Optional[HandInputEvent]:
        """Process pinch-specific position (thumb-index midpoint).

        Used for more accurate pinch cursor positioning.
        """
        if not self._enabled:
            return None

        ts = timestamp or time.perf_counter()

        # Average thumb and index positions for stable pinch cursor
        position_x = (thumb_x + index_x) / 2.0
        position_y = (thumb_y + index_y) / 2.0

        if confidence < self._confidence_threshold:
            return None

        event = HandInputEvent(
            position_x=position_x,
            position_y=position_y,
            gesture=HandGesture.PINCH,
            confidence=confidence,
            timestamp=ts,
            hand_label=hand_label,
        )

        self._last_event = event
        return event

    @property
    def last_event(self) -> Optional[HandInputEvent]:
        return self._last_event

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True
        logger.debug("HandController enabled")

    def disable(self) -> None:
        self._enabled = False
        logger.debug("HandController disabled")

    def set_preferred_hand(self, hand: str) -> None:
        """Set preferred hand: 'left', 'right', or 'both'."""
        self._preferred_hand = hand.lower()
        logger.debug("Preferred hand: %s", self._preferred_hand)

    def set_confidence_threshold(self, threshold: float) -> None:
        self._confidence_threshold = max(0.0, min(1.0, threshold))

    def get_gesture_command(self, gesture_name: str) -> Optional[str]:
        """Get the command mapped to a gesture name (legacy string-based).

        Returns None if gesture is not configured or disabled.
        """
        config = self._gesture_configs.get(gesture_name)
        if not config:
            return None
        if not config.get("enabled", True):
            return None
        return config.get("command")

    def get_gesture_command_by_enum(self, gesture: Gesture) -> Optional[str]:
        """Get the command mapped to a Gesture enum value.

        Uses gesture.value for config lookup (e.g., "pinch", "open_palm").
        Returns None if gesture is not configured or disabled.
        """
        config = self._gesture_configs.get(gesture.value)
        if not config:
            return None
        if not config.get("enabled", True):
            return None
        return config.get("command")

    def get_gesture_cooldown(self, gesture_name: str) -> float:
        """Get cooldown in seconds for a gesture (legacy string-based)."""
        config = self._gesture_configs.get(gesture_name)
        if not config:
            return 0.0
        return config.get("cooldown", 300) / 1000.0  # Convert ms to seconds

    def get_gesture_cooldown_by_enum(self, gesture: Gesture) -> float:
        """Get cooldown in seconds for a Gesture enum value."""
        return self.get_gesture_cooldown(gesture.value)

    # ── Internal ───────────────────────────────────────────────────

    def _map_gesture(self, name: str) -> HandGesture:
        """Map gesture name string to HandGesture enum."""
        mapping = {
            "Open_Palm": HandGesture.OPEN_PALM,
            "open_palm": HandGesture.OPEN_PALM,
            "Closed_Fist": HandGesture.FIST,
            "fist": HandGesture.FIST,
            "Pinch": HandGesture.PINCH,
            "pinch": HandGesture.PINCH,
            "Thumb_Up": HandGesture.THUMB_UP,
            "thumb_up": HandGesture.THUMB_UP,
            "Victory": HandGesture.PEACE,
            "victory": HandGesture.PEACE,
            "peace": HandGesture.PEACE,
            "Pointing_Up": HandGesture.POINT_UP,
            "pointing_up": HandGesture.POINT_UP,
            "ILoveYou": HandGesture.POINT_UP,
        }
        return mapping.get(name, HandGesture.NONE)

    def _check_cooldown(self, gesture_name: str, timestamp: float) -> bool:
        """Check if gesture is past its cooldown period."""
        if gesture_name not in self._gesture_cooldowns:
            self._gesture_cooldowns[gesture_name] = timestamp
            return True

        last_time = self._gesture_cooldowns[gesture_name]
        cooldown = self.get_gesture_cooldown(gesture_name)

        if (timestamp - last_time) >= cooldown:
            self._gesture_cooldowns[gesture_name] = timestamp
            return True

        return False
