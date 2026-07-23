"""
Gesture Router — Maps hand gestures to actions

Handles:
- Multi-hand pinch detection (any hand = CLICK)
- Gesture → action mapping with cooldown
- Thread-safe action queue for main thread processing
- Hand-lost buffer to prevent cursor flicker

Events are routed through action_queue so they fire on the main thread.
Direct EventBus calls from perception threads are avoided.
"""

import math
import time
import queue
import logging
import threading


logger = logging.getLogger("Aether.GestureRouter")

# ─── Config (tuned for easy detection) ───────────────────────────
PINCH_THRESHOLD = 0.08
GESTURE_COOLDOWN = 0.8
CLOSED_FIST_HOLD = 1.2     # Closed_Fist must be held 1.2s to trigger
HAND_LOST_FRAMES = 6


class GestureRouter:
    """Routes hand gestures to actions via EventBus and thread-safe queue."""

    def __init__(self, action_queue: queue.Queue = None, event_bus=None):
        self.action_queue = action_queue or queue.Queue()
        self.event_bus = event_bus
        self._last_gesture = None
        self._last_gesture_time = 0.0
        self._was_pinching = False
        self._hands = []
        self._objects = []
        self._lock = threading.Lock()
        self._hand_lost_counter = 0
        self._last_cursor = None
        self._last_gesture_name = "Unknown"
        self._fist_hold_start = 0.0  # tracks when Closed_Fist started

    @property
    def hands(self):
        with self._lock:
            return list(self._hands)

    @property
    def objects(self):
        with self._lock:
            return list(self._objects)

    def on_hand_update(self, event):
        """Handle HAND_DETECTED events. Checks ALL hands for pinch."""
        hands = event.data.get("hands", [])

        with self._lock:
            self._hands = hands

        if not hands:
            self._hand_lost_counter += 1
            if self._hand_lost_counter >= HAND_LOST_FRAMES:
                self._was_pinching = False
                self._last_cursor = None
                self._hand_lost_counter = 0
                self.action_queue.put(("no_hands", None))
            elif self._last_cursor is not None:
                self.action_queue.put(("cursor_update", {
                    "cursor": self._last_cursor,
                    "gesture": self._last_gesture_name,
                    "is_pinch": False,
                    "hand_count": 0,
                }))
            return

        self._hand_lost_counter = 0
        any_pinching = False
        best_cursor = None
        best_gesture = "Unknown"

        for hand in hands:
            lm = hand.get("landmarks", [])
            if not lm or len(lm) < 21:
                continue

            idx = lm[8]
            thumb = lm[4]
            dx = idx["x"] - thumb["x"]
            dy = idx["y"] - thumb["y"]
            dist = math.sqrt(dx * dx + dy * dy)
            is_pinch = dist < PINCH_THRESHOLD

            if is_pinch:
                any_pinching = True

            if best_cursor is None:
                best_cursor = (idx["x"], idx["y"])
                best_gesture = hand.get("gesture", "Unknown")

        self._last_cursor = best_cursor
        self._last_gesture_name = best_gesture

        # ── Gesture → action (route through action_queue for main thread)
        now = time.time()
        gesture = best_gesture
        cooldown_ok = (gesture != self._last_gesture) or (now - self._last_gesture_time) > GESTURE_COOLDOWN

        # Closed_Fist requires hold time to avoid accidental triggers
        if gesture == "Closed_Fist":
            if self._fist_hold_start == 0.0:
                self._fist_hold_start = now
                fist_hold_ok = False
            else:
                fist_hold_ok = (now - self._fist_hold_start) >= CLOSED_FIST_HOLD
        else:
            self._fist_hold_start = 0.0
            fist_hold_ok = True

        if gesture != "Unknown" and gesture != "Pointing_Up" and cooldown_ok and fist_hold_ok:
            if self.event_bus:
                self._queue_gesture_event(gesture)
            self._last_gesture = gesture
            self._last_gesture_time = now
            if gesture == "Closed_Fist":
                self._fist_hold_start = 0.0

        # ── Cursor + state update (must be before pinch_click) ────
        self.action_queue.put(("cursor_update", {
            "cursor": best_cursor,
            "gesture": best_gesture,
            "is_pinch": any_pinching,
            "hand_count": len(hands),
        }))

        # ── Pinch = CLICK (any hand, edge-triggered) ─────────────
        if any_pinching and not self._was_pinching:
            self.action_queue.put(("pinch_click", best_cursor))
        self._was_pinching = any_pinching

    def on_object_update(self, event):
        """Handle OBJECT_DETECTED events."""
        with self._lock:
            self._objects = event.data.get("objects", [])

    def _queue_gesture_event(self, gesture):
        """Queue EventBus events for main-thread dispatch via action_queue.

        This ensures Qt widget operations (show/hide) happen on the main thread.
        Also prevents re-emitting MENU_OPEN when menu is already open.
        """
        from core.event_bus import EventType

        if gesture == "Open_Palm":
            self.action_queue.put(("emit_event", EventType.MENU_OPEN, {}, True))
        elif gesture == "Closed_Fist":
            self.action_queue.put(("emit_event", EventType.MENU_CLOSE, {}, False))
            self.action_queue.put(("emit_event", EventType.UI_CLOSE, {}, False))
        elif gesture == "Victory":
            self.action_queue.put(("emit_event", EventType.PANEL_SHOW_REQUESTED, {"panel": "developer"}, False))
        elif gesture == "ILoveYou":
            self.action_queue.put(("emit_event", EventType.PANEL_SHOW_REQUESTED, {"panel": "settings"}, False))
        elif gesture == "Thumb_Up":
            self.action_queue.put(("emit_event", EventType.MODE_CHANGED, {"mode": "normal"}, False))
        elif gesture == "Thumb_Down":
            self.action_queue.put(("emit_event", EventType.MODE_CHANGED, {"mode": "developer"}, False))


def handle_gesture_action(gesture, ui):
    """Execute gesture action on the main thread (safe for Qt)."""
    if gesture == "Open_Palm":
        ui.show()
        ui.raise_()
        ui.activateWindow()
        ui.show_panel("system")
        logger.info("Gesture: Open_Palm -> show system panel")
    elif gesture == "Victory":
        ui.show()
        ui.raise_()
        ui.show_panel("developer")
        logger.info("Gesture: Victory -> show developer panel")
    elif gesture == "ILoveYou":
        ui.show()
        ui.raise_()
        ui.show_panel("settings")
        logger.info("Gesture: ILoveYou -> show settings panel")
    elif gesture == "Closed_Fist":
        ui.hide()
        logger.info("Gesture: Closed_Fist -> hide UI")
    elif gesture == "Thumb_Up":
        ui.set_mode("normal")
        logger.info("Gesture: Thumb_Up -> normal mode")
    elif gesture == "Thumb_Down":
        ui.set_mode("developer")
        logger.info("Gesture: Thumb_Down -> developer mode")


def handle_pinch_click(cursor, ui):
    """Pinch = CLICK. Log it, could trigger button press."""
    logger.info(f"Pinch CLICK at {cursor}")
