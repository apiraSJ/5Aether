"""
Gesture Action System — 5 Core Gestures

Maps hand gestures to Aether UI commands via simple finger counting.

Flow:
  HandLandmarks → GestureEngine → GestureEvent → GestureActionExecutor → Popup Window
"""

import logging
import math
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from vision.hand_landmarks import Landmark


# ─── 5 Core Gesture Types ────────────────────────────────────────
class GestureType(Enum):
    FIST = "Closed_Fist"
    OPEN_PALM = "Open_Palm"
    POINT = "Pointing_Up"
    THUMBS_UP = "Thumb_Up"
    THUMB_DOWN = "Thumb_Down"

    UNKNOWN = "Unknown"


# ─── Command Actions ─────────────────────────────────────────────
class ActionType(Enum):
    TOGGLE_UI = "toggle_ui"
    MOVE_CURSOR = "move_cursor"
    CLICK = "click"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    NO_ACTION = "no_action"


# ─── Gesture → Action Mapping ─────────────────────────────────────
DEFAULT_GESTURE_MAP: Dict[GestureType, ActionType] = {
    GestureType.FIST: ActionType.CANCEL,
    GestureType.OPEN_PALM: ActionType.TOGGLE_UI,
    GestureType.POINT: ActionType.MOVE_CURSOR,
    GestureType.THUMBS_UP: ActionType.CONFIRM,
    GestureType.THUMB_DOWN: ActionType.CANCEL,
}

GESTURE_COMMAND_NAMES: Dict[GestureType, str] = {
    GestureType.FIST: "Cancel / Close",
    GestureType.OPEN_PALM: "Toggle UI",
    GestureType.POINT: "Move Cursor",
    GestureType.THUMBS_UP: "Confirm / Accept",
    GestureType.THUMB_DOWN: "Reject / Deny",
    GestureType.UNKNOWN: "No command",
}


@dataclass
class GestureAction:
    action: ActionType
    gesture: GestureType
    position: tuple = (0.5, 0.5)
    confidence: float = 0.0
    timestamp_ms: int = 0


# ─── Finger Detection ────────────────────────────────────────────
class HandFeatures:
    """Simple finger extension detection from 21 landmarks."""

    @staticmethod
    def is_finger_extended(lm, finger: str) -> bool:
        """Check if a finger is extended by comparing tip vs PIP joint."""
        tip_ids = {
            "thumb": Landmark.THUMB_TIP,
            "index": Landmark.INDEX_FINGER_TIP,
            "middle": Landmark.MIDDLE_FINGER_TIP,
            "ring": Landmark.RING_FINGER_TIP,
            "pinky": Landmark.PINKY_TIP,
        }
        pip_ids = {
            "thumb": Landmark.THUMB_IP,
            "index": Landmark.INDEX_FINGER_PIP,
            "middle": Landmark.MIDDLE_FINGER_PIP,
            "ring": Landmark.RING_FINGER_PIP,
            "pinky": Landmark.PINKY_PIP,
        }

        if finger == "thumb":
            mcp = lm[Landmark.THUMB_MCP]
            tip = lm[tip_ids[finger]]
            ip = lm[pip_ids[finger]]
            return abs(tip.x - mcp.x) > abs(ip.x - mcp.x)

        tip = lm[tip_ids[finger]]
        pip = lm[pip_ids[finger]]
        return tip.y < pip.y

    @staticmethod
    def count_extended(lm) -> int:
        """Count how many fingers are extended."""
        count = 0
        for f in ["thumb", "index", "middle", "ring", "pinky"]:
            if HandFeatures.is_finger_extended(lm, f):
                count += 1
        return count

    @staticmethod
    def pinch_distance(lm) -> float:
        """Distance between thumb tip and index tip (normalized)."""
        t = lm[Landmark.THUMB_TIP]
        i = lm[Landmark.INDEX_FINGER_TIP]
        return math.sqrt((t.x - i.x) ** 2 + (t.y - i.y) ** 2)

    @staticmethod
    def hand_center(lm) -> tuple:
        """Center of the hand (wrist + middle MCP average)."""
        w = lm[Landmark.WRIST]
        m = lm[Landmark.MIDDLE_FINGER_MCP]
        return ((w.x + m.x) / 2, (w.y + m.y) / 2)

    @staticmethod
    def index_tip_position(lm) -> tuple:
        """Position of the index fingertip (for cursor)."""
        tip = lm[Landmark.INDEX_FINGER_TIP]
        return (tip.x, tip.y)
