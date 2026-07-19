import logging
import numpy as np
import cv2


# MediaPipe hand landmark connections (standard 21-landmark skeleton)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),        # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),        # Index
    (5, 9), (9, 10), (10, 11), (11, 12),   # Middle
    (9, 13), (13, 14), (14, 15), (15, 16), # Ring
    (13, 17), (17, 18), (18, 19), (19, 20),# Pinky
    (0, 17),                               # Palm base
]

# Color per handedness (BGR)
HANDEDNESS_COLORS = {
    "Left": (0, 200, 255),   # orange
    "Right": (0, 255, 120),  # green
}


class HandOverlay:
    """Draws MediaPipe hand landmarks + connections and the gesture label
    onto a numpy (BGR) frame."""

    def __init__(self):
        self.logger = logging.getLogger("Aether.HandOverlay")
        self._landmarks = None
        self._gesture = None
        self._menu_items = []

    def update(self, hand_results, gesture=None):
        self._gesture = gesture
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

    def draw(self, frame: np.ndarray, hand_results, gesture: str = None) -> np.ndarray:
        """Draw all detected hands onto `frame` (BGR). Returns the frame."""
        if hand_results is None or not hand_results.hands:
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
            label = gesture or hand.handedness
            if label:
                cv2.putText(
                    frame, label, (int(lm[0].x * w), int(lm[0].y * h) - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2
                )

        return frame
