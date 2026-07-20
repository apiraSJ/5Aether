import logging
import numpy as np
import cv2
from vision.hand_landmarks import Landmark, HAND_CONNECTIONS


# Color per handedness (BGR)
HANDEDNESS_COLORS = {
    "Left": (0, 200, 255),   # orange
    "Right": (0, 255, 120),  # green
}

# Color per action type (BGR)
ACTION_COLORS = {
    "cursor_move": (0, 255, 0),
    "cursor_click": (0, 255, 255),
    "cursor_confirm": (0, 200, 255),
    "ui_toggle": (255, 200, 0),
    "panel_next": (255, 150, 0),
    "panel_prev": (150, 150, 0),
    "scroll": (200, 0, 255),
    "drag_start": (0, 0, 255),
    "drag_move": (0, 0, 200),
    "drag_end": (128, 128, 128),
    "cancel": (0, 0, 200),
    "mode_switch": (200, 200, 0),
}

# Gesture display labels (human-readable)
GESTURE_LABELS = {
    "open_palm": "OPEN",
    "point": "POINT",
    "pinch": "PINCH",
    "fist": "FIST",
    "peace": "PEACE",
    "thumbs_up": "THUMB UP",
    "victory": "VICTORY",
    "call": "CALL",
    "swipe_left": "SWIPE L",
    "swipe_right": "SWIPE R",
    "swipe_up": "SWIPE UP",
    "swipe_down": "SWIPE DN",
    "grab": "GRAB",
    "release": "RELEASE",
    "scroll_up": "SCROLL UP",
    "scroll_down": "SCROLL DN",
}


class HandOverlay:
    """Draws MediaPipe hand landmarks + connections, gesture label,
    cursor crosshair, and action overlay onto a numpy (BGR) frame."""

    def __init__(self):
        self.logger = logging.getLogger("Aether.HandOverlay")
        self._landmarks = None
        self._gesture = None
        self._action = None
        self._menu_items = []

    def update(self, hand_results, gesture=None, action=None):
        self._gesture = gesture
        self._action = action
        if hand_results and hand_results.hands:
            self._landmarks = hand_results.hands[0].landmarks
        else:
            self._landmarks = None

    def get_landmarks(self):
        return self._landmarks

    def get_gesture(self):
        return self._gesture

    def set_menu_items(self, items: list):
        self._menu_items = items

    def get_menu_items(self):
        return self._menu_items

    def draw(self, frame: np.ndarray, hand_results, gesture: str = None,
             action: str = None, cursor: tuple = None,
             is_dragging: bool = False) -> np.ndarray:
        """Draw all detected hands, cursor, and action info onto `frame` (BGR).
        Returns the frame."""
        if hand_results is None or not hand_results.hands:
            # Still draw cursor if we have one
            if cursor:
                self._draw_cursor(frame, cursor, is_dragging)
            return frame

        h, w = frame.shape[:2]

        for hand in hand_results.hands:
            color = HANDEDNESS_COLORS.get(hand.handedness, (0, 255, 255))
            lm = hand.landmarks
            if not lm or len(lm) < 21:
                continue

            # Connections
            for a, b in HAND_CONNECTIONS:
                pa = (int(lm[a].x * w), int(lm[a].y * h))
                pb = (int(lm[b].x * w), int(lm[b].y * h))
                cv2.line(frame, pa, pb, color, 2)

            # Landmark dots
            for p in lm:
                px = int(p.x * w)
                py = int(p.y * h)
                cv2.circle(frame, (px, py), 3, color, -1)

            # Gesture label near wrist
            label = GESTURE_LABELS.get(gesture, gesture) if gesture else hand.handedness
            if label:
                lx = int(lm[0].x * w)
                ly = int(lm[0].y * h) - 12
                # Background rect for readability
                (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)
                cv2.rectangle(frame, (lx - 2, ly - th - 4), (lx + tw + 4, ly + 4), (0, 0, 0), -1)
                cv2.putText(frame, label, (lx, ly),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # Action label below gesture
            if action:
                action_label = action.upper()
                al_color = ACTION_COLORS.get(action, (255, 255, 255))
                ax = int(lm[0].x * w)
                ay = int(lm[0].y * h) + 18
                (aw, ah), _ = cv2.getTextSize(action_label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                cv2.rectangle(frame, (ax - 2, ay - ah - 2), (ax + aw + 4, ay + 4), (0, 0, 0), -1)
                cv2.putText(frame, action_label, (ax, ay),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, al_color, 1)

        # Cursor crosshair
        if cursor:
            self._draw_cursor(frame, cursor, is_dragging)

        return frame

    def _draw_cursor(self, frame, cursor: tuple, is_dragging: bool):
        """Draw a crosshair at the normalized cursor position."""
        h, w = frame.shape[:2]
        cx = int(cursor[0] * w)
        cy = int(cursor[1] * h)

        # Clamp to frame
        cx = max(0, min(w - 1, cx))
        cy = max(0, min(h - 1, cy))

        size = 12
        color = (0, 200, 255) if is_dragging else (0, 255, 255)
        thickness = 2

        # Crosshair lines
        cv2.line(frame, (cx - size, cy), (cx + size, cy), color, thickness)
        cv2.line(frame, (cx, cy - size), (cx, cy + size), color, thickness)

        # Outer circle
        cv2.circle(frame, (cx, cy), size + 4, color, 1)

        # Center dot
        cv2.circle(frame, (cx, cy), 2, (0, 0, 255), -1)

        # Status label
        if is_dragging:
            cv2.putText(frame, "DRAGGING", (cx + 16, cy - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
