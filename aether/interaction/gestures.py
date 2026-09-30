"""Gesture — canonical gesture enum for all input sources.

All gesture names from MediaPipe, Voice, or other input sources
are normalized to this enum. The system uses Gesture enum internally,
not strings.

Usage:
    from aether.interaction.gestures import Gesture

    gesture = Gesture.from_mediapipe("Open_Palm")
    assert gesture == Gesture.OPEN_PALM

    # Config lookup
    command = gesture_config.get(gesture.value, {}).get("command")
"""

from __future__ import annotations

from enum import Enum


class Gesture(Enum):
    """Canonical gesture identifiers.

    All input sources (MediaPipe, Voice, XR) normalize to these values.
    The .value is used for config lookup and serialization.
    """
    NONE = "none"
    PINCH = "pinch"
    OPEN_PALM = "open_palm"
    CLOSED_FIST = "closed_fist"
    THUMB_UP = "thumb_up"
    PEACE = "peace"
    POINT_UP = "point_up"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    SWIPE_UP = "swipe_up"
    SWIPE_DOWN = "swipe_down"

    @classmethod
    def from_mediapipe(cls, name: str) -> "Gesture":
        """Normalize MediaPipe gesture name to canonical Gesture enum.

        Handles variations in naming:
        - "Open_Palm", "OPEN_PALM", "openPalm", "open_palm"
        - "Closed_Fist", "CLOSED_FIST", "closedFist", "closed_fist"
        - etc.
        """
        if not name:
            return cls.NONE

        # Normalize to lowercase for consistent lookup
        normalized = name.lower().replace("_", "").replace("-", "")

        mapping = {
            "pinch": cls.PINCH,
            "openpalm": cls.OPEN_PALM,
            "closedfist": cls.CLOSED_FIST,
            "thumbup": cls.THUMB_UP,
            "victory": cls.PEACE,
            "peace": cls.PEACE,
            "pointingup": cls.POINT_UP,
            "pointup": cls.POINT_UP,
            "iloveyou": cls.POINT_UP,
            "swipeleft": cls.SWIPE_LEFT,
            "swiperight": cls.SWIPE_RIGHT,
            "swipeup": cls.SWIPE_UP,
            "swipedown": cls.SWIPE_DOWN,
        }

        return mapping.get(normalized, cls.NONE)

    @classmethod
    def from_string(cls, name: str) -> "Gesture":
        """Convert a string gesture name to Gesture enum.

        Accepts both normalized forms ("pinch") and legacy forms ("Pinch").
        """
        return cls.from_mediapipe(name)

    @classmethod
    def from_config(cls, name: str) -> "Gesture":
        """Convert config string to Gesture enum.

        Config uses lowercase values like "pinch", "open_palm", etc.
        """
        normalized = name.lower().replace("-", "_")
        for gesture in cls:
            if gesture.value == normalized:
                return gesture
        return cls.NONE
