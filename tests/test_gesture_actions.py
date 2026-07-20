import sys
import os
import math
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import unittest

from vision.gesture_actions import (
    GestureType, ActionType, GestureAction,
    HandFeatures, DEFAULT_GESTURE_MAP, GESTURE_COMMAND_NAMES
)
from vision.hand_landmarks import Landmark
from vision.hand_tracker import HandLandmark, HandData, HandResults
from vision.gesture_engine import GestureEngine, GestureEvent
from vision.gesture_executor import GestureActionExecutor, GestureActionState
from core.event_bus import EventBus, EventType


def _make_landmarks(extended_fingers=None, thumb_up=True, pinch_close=False):
    """Build 21 HandLandmark objects with controllable finger extension.
    extended_fingers: list of finger names that are extended.
    If None, defaults to all 5 extended (open palm).
    """
    if extended_fingers is None:
        extended_fingers = ["thumb", "index", "middle", "ring", "pinky"]

    lm = [HandLandmark(x=0.5, y=0.5, z=0.0)] * 21

    # Wrist
    lm[Landmark.WRIST] = HandLandmark(x=0.5, y=0.8, z=0.0)

    # Thumb — extension checked by x-distance from MCP
    thumb_out = "thumb" in extended_fingers
    lm[Landmark.THUMB_MCP] = HandLandmark(x=0.45, y=0.65, z=0.0)
    lm[Landmark.THUMB_IP] = HandLandmark(x=0.44, y=0.60, z=0.0)
    # Extended: tip far from mcp (x=0.32). Not extended: tip close to mcp (x=0.448)
    lm[Landmark.THUMB_TIP] = HandLandmark(x=0.32 if thumb_out else 0.445, y=0.55 if thumb_up else 0.75, z=0.0)

    # Index
    idx_out = "index" in extended_fingers
    lm[Landmark.INDEX_FINGER_MCP] = HandLandmark(x=0.48, y=0.55, z=0.0)
    lm[Landmark.INDEX_FINGER_PIP] = HandLandmark(x=0.47, y=0.48 if idx_out else 0.57, z=0.0)
    lm[Landmark.INDEX_FINGER_TIP] = HandLandmark(x=0.46, y=0.40 if idx_out else 0.62, z=0.0)

    # Middle
    mid_out = "middle" in extended_fingers
    lm[Landmark.MIDDLE_FINGER_MCP] = HandLandmark(x=0.50, y=0.55, z=0.0)
    lm[Landmark.MIDDLE_FINGER_PIP] = HandLandmark(x=0.50, y=0.46 if mid_out else 0.57, z=0.0)
    lm[Landmark.MIDDLE_FINGER_TIP] = HandLandmark(x=0.50, y=0.38 if mid_out else 0.62, z=0.0)

    # Ring
    ring_out = "ring" in extended_fingers
    lm[Landmark.RING_FINGER_MCP] = HandLandmark(x=0.52, y=0.55, z=0.0)
    lm[Landmark.RING_FINGER_PIP] = HandLandmark(x=0.53, y=0.48 if ring_out else 0.57, z=0.0)
    lm[Landmark.RING_FINGER_TIP] = HandLandmark(x=0.54, y=0.40 if ring_out else 0.62, z=0.0)

    # Pinky
    pink_out = "pinky" in extended_fingers
    lm[Landmark.PINKY_MCP] = HandLandmark(x=0.55, y=0.57, z=0.0)
    lm[Landmark.PINKY_PIP] = HandLandmark(x=0.57, y=0.50 if pink_out else 0.59, z=0.0)
    lm[Landmark.PINKY_TIP] = HandLandmark(x=0.59, y=0.43 if pink_out else 0.63, z=0.0)

    # Pinch override: bring thumb and index tips together
    if pinch_close:
        lm[Landmark.THUMB_TIP] = HandLandmark(x=0.45, y=0.45, z=0.0)
        lm[Landmark.INDEX_FINGER_TIP] = HandLandmark(x=0.46, y=0.45, z=0.0)

    return lm


def _make_hand(extended_fingers=None, thumb_up=True, pinch_close=False):
    lm = _make_landmarks(extended_fingers, thumb_up, pinch_close)
    return HandData(
        landmarks=lm,
        world_landmarks=[],
        handedness="Right",
        confidence=0.9,
        bounding_box=(100, 100, 400, 400),
    )


def _make_hand_results(hands=None):
    if hands is None:
        hands = [_make_hand()]
    return HandResults(hands=hands, timestamp_ms=int(time.time() * 1000))


# ─── Tests ────────────────────────────────────────────────────────

class TestGestureType(unittest.TestCase):
    def test_five_core_gestures(self):
        core = [GestureType.FIST, GestureType.OPEN_PALM, GestureType.POINT,
                GestureType.THUMBS_UP, GestureType.THUMB_DOWN]
        self.assertEqual(len(core), 5)
        for gt in core:
            self.assertNotEqual(gt, GestureType.UNKNOWN)

    def test_unknown_gesture(self):
        self.assertEqual(GestureType.UNKNOWN.value, "Unknown")


class TestActionType(unittest.TestCase):
    def test_six_actions(self):
        actions = [ActionType.TOGGLE_UI, ActionType.MOVE_CURSOR, ActionType.CLICK,
                   ActionType.CONFIRM, ActionType.CANCEL, ActionType.NO_ACTION]
        self.assertEqual(len(actions), 6)


class TestDefaultGestureMap(unittest.TestCase):
    def test_all_core_gestures_mapped(self):
        for gt in GestureType:
            if gt == GestureType.UNKNOWN:
                continue
            action = DEFAULT_GESTURE_MAP.get(gt)
            self.assertIsNotNone(action, f"{gt.value} has no mapping")
            self.assertNotEqual(action, ActionType.NO_ACTION, f"{gt.value} maps to NO_ACTION")

    def test_fist_maps_to_cancel(self):
        self.assertEqual(DEFAULT_GESTURE_MAP[GestureType.FIST], ActionType.CANCEL)

    def test_open_palm_maps_to_toggle_ui(self):
        self.assertEqual(DEFAULT_GESTURE_MAP[GestureType.OPEN_PALM], ActionType.TOGGLE_UI)

    def test_point_maps_to_move_cursor(self):
        self.assertEqual(DEFAULT_GESTURE_MAP[GestureType.POINT], ActionType.MOVE_CURSOR)

    def test_thumbs_up_maps_to_confirm(self):
        self.assertEqual(DEFAULT_GESTURE_MAP[GestureType.THUMBS_UP], ActionType.CONFIRM)

    def test_thumbs_down_maps_to_cancel(self):
        self.assertEqual(DEFAULT_GESTURE_MAP[GestureType.THUMB_DOWN], ActionType.CANCEL)


class TestGestureCommandNames(unittest.TestCase):
    def test_all_gestures_have_names(self):
        for gt in GestureType:
            name = GESTURE_COMMAND_NAMES.get(gt)
            self.assertIsNotNone(name, f"{gt.value} has no command name")
            self.assertIsInstance(name, str)
            self.assertTrue(len(name) > 0)


class TestHandFeatures(unittest.TestCase):
    def test_pinch_distance_close(self):
        lm = _make_landmarks(pinch_close=True)
        dist = HandFeatures.pinch_distance(lm)
        self.assertLess(dist, 0.05)

    def test_pinch_distance_far(self):
        lm = _make_landmarks(extended_fingers=["thumb", "index", "middle"])
        dist = HandFeatures.pinch_distance(lm)
        self.assertGreater(dist, 0.05)

    def test_count_extended_open(self):
        lm = _make_landmarks(extended_fingers=["thumb", "index", "middle", "ring", "pinky"])
        self.assertEqual(HandFeatures.count_extended(lm), 5)

    def test_count_extended_fist(self):
        lm = _make_landmarks(extended_fingers=[])
        self.assertEqual(HandFeatures.count_extended(lm), 0)

    def test_count_extended_point(self):
        lm = _make_landmarks(extended_fingers=["index"])
        self.assertEqual(HandFeatures.count_extended(lm), 1)

    def test_is_finger_extended(self):
        lm = _make_landmarks(extended_fingers=["index"])
        self.assertTrue(HandFeatures.is_finger_extended(lm, "index"))
        self.assertFalse(HandFeatures.is_finger_extended(lm, "middle"))
        self.assertFalse(HandFeatures.is_finger_extended(lm, "ring"))

    def test_hand_center(self):
        lm = _make_landmarks()
        cx, cy = HandFeatures.hand_center(lm)
        self.assertAlmostEqual(cx, 0.5, places=1)
        self.assertGreater(cy, 0.0)

    def test_index_tip_position(self):
        lm = _make_landmarks(extended_fingers=["index"])
        x, y = HandFeatures.index_tip_position(lm)
        self.assertGreater(x, 0.0)
        self.assertLess(y, 0.8)


class TestGestureEngineStatic(unittest.TestCase):
    def setUp(self):
        self.engine = GestureEngine({"dwell_time_ms": 0})

    def _recognize_with_hand(self, fingers, thumb_up=True):
        hand = _make_hand(extended_fingers=fingers, thumb_up=thumb_up)
        results = _make_hand_results([hand])
        events = self.engine.update(results)
        return events

    def test_open_palm(self):
        events = self._recognize_with_hand(["thumb", "index", "middle", "ring", "pinky"])
        gestures = [e.gesture for e in events]
        self.assertIn(GestureType.OPEN_PALM, gestures)

    def test_point(self):
        events = self._recognize_with_hand(["index"])
        gestures = [e.gesture for e in events]
        self.assertIn(GestureType.POINT, gestures)

    def test_fist(self):
        events = self._recognize_with_hand([])
        gestures = [e.gesture for e in events]
        self.assertIn(GestureType.FIST, gestures)

    def test_thumbs_up(self):
        events = self._recognize_with_hand(["thumb"], thumb_up=True)
        gestures = [e.gesture for e in events]
        self.assertIn(GestureType.THUMBS_UP, gestures)

    def test_thumbs_down(self):
        events = self._recognize_with_hand(["thumb"], thumb_up=False)
        gestures = [e.gesture for e in events]
        self.assertIn(GestureType.THUMB_DOWN, gestures)

    def test_unknown_for_two_fingers(self):
        events = self._recognize_with_hand(["index", "middle"])
        gestures = [e.gesture for e in events]
        self.assertEqual(gestures, [])

    def test_cursor_tracking(self):
        hand = _make_hand(extended_fingers=["index"])
        results = _make_hand_results([hand])
        self.engine.update(results)
        self.engine.update(results)
        cx, cy = self.engine.get_cursor_position()
        self.assertGreater(cx, 0.0)
        self.assertLess(cx, 1.0)

    def test_no_hand_resets_last_gesture(self):
        hand = _make_hand(extended_fingers=[])
        results = _make_hand_results([hand])
        self.engine.update(results)
        self.engine.update(results)
        empty = HandResults(hands=[], timestamp_ms=int(time.time() * 1000))
        self.engine.update(empty)
        self.assertIsNone(self.engine._last_gesture)


class TestGestureActionExecutor(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.engine = GestureEngine({"dwell_time_ms": 0})
        self.executor = GestureActionExecutor(self.bus, self.engine)
        self.emitted = []
        self.bus.subscribe(EventType.GESTURE_RECOGNIZED, lambda e: self.emitted.append(e))

    def _emit_gesture(self, gesture_type, position=(0.5, 0.5)):
        ge = GestureEvent(
            gesture=gesture_type,
            hand=None,
            position=position,
            confidence=0.9,
            timestamp_ms=int(time.time() * 1000),
        )
        return self.executor.process_events([ge])

    def test_open_palm_toggles_ui(self):
        actions = self._emit_gesture(GestureType.OPEN_PALM)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, ActionType.TOGGLE_UI)
        self.assertTrue(any(e.data.get("action") == "toggle_ui" for e in self.emitted))

    def test_point_moves_cursor(self):
        ge = GestureEvent(
            gesture=GestureType.POINT,
            hand=None,
            position=(0.3, 0.7),
            confidence=0.9,
            timestamp_ms=int(time.time() * 1000),
        )
        actions = self.executor.process_events([ge])
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, ActionType.MOVE_CURSOR)
        self.assertAlmostEqual(actions[0].position[0], 0.3, places=1)
        self.assertAlmostEqual(actions[0].position[1], 0.7, places=1)

    def test_fist_cancels(self):
        actions = self._emit_gesture(GestureType.FIST)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, ActionType.CANCEL)

    def test_thumbs_up_confirms(self):
        actions = self._emit_gesture(GestureType.THUMBS_UP)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, ActionType.CONFIRM)

    def test_thumbs_down_cancels(self):
        actions = self._emit_gesture(GestureType.THUMB_DOWN)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action, ActionType.CANCEL)

    def test_unknown_gesture_ignored(self):
        actions = self._emit_gesture(GestureType.UNKNOWN)
        self.assertEqual(len(actions), 0)

    def test_cooldown_prevents_rapid_fire(self):
        self.executor._state.cooldown_ms = 500
        actions1 = self._emit_gesture(GestureType.OPEN_PALM)
        self.assertEqual(len(actions1), 1)
        actions2 = self._emit_gesture(GestureType.OPEN_PALM)
        self.assertEqual(len(actions2), 0)

    def test_different_gesture_bypasses_cooldown(self):
        self.executor._state.cooldown_ms = 500
        actions1 = self._emit_gesture(GestureType.OPEN_PALM)
        self.assertEqual(len(actions1), 1)
        actions2 = self._emit_gesture(GestureType.FIST)
        self.assertEqual(len(actions2), 1)

    def test_cooldown_zero_allows_rapid_fire(self):
        self.executor._state.cooldown_ms = 0
        actions1 = self._emit_gesture(GestureType.OPEN_PALM)
        self.assertEqual(len(actions1), 1)
        actions2 = self._emit_gesture(GestureType.OPEN_PALM)
        self.assertEqual(len(actions2), 1)

    def test_cursor_tracking(self):
        self._emit_gesture(GestureType.OPEN_PALM)
        cx, cy = self.executor.get_cursor()
        self.assertGreater(cx, 0.0)
        self.assertLess(cx, 1.0)


class TestPerceptionSnapshot(unittest.TestCase):
    def test_snapshot_has_action_fields(self):
        from core.perception_worker import PerceptionSnapshot
        snap = PerceptionSnapshot()
        self.assertIsInstance(snap.actions, list)
        self.assertEqual(snap.cursor, (0.5, 0.5))
        self.assertFalse(snap.is_dragging)


class TestGestureEventBusIntegration(unittest.TestCase):
    def test_full_round_trip(self):
        bus = EventBus()
        engine = GestureEngine({"dwell_time_ms": 0})
        executor = GestureActionExecutor(bus, engine)

        received_events = []
        bus.subscribe(EventType.GESTURE_RECOGNIZED, lambda e: received_events.append(e))

        ge = GestureEvent(
            gesture=GestureType.OPEN_PALM,
            hand=None,
            position=(0.5, 0.5),
            confidence=0.9,
            timestamp_ms=int(time.time() * 1000),
        )
        executor.process_events([ge])

        event_types = [e.type for e in received_events]
        self.assertIn(EventType.GESTURE_RECOGNIZED, event_types)

    def test_gesture_recognized_data_fields(self):
        bus = EventBus()
        engine = GestureEngine({"dwell_time_ms": 0})
        executor = GestureActionExecutor(bus, engine)

        received = []
        bus.subscribe(EventType.GESTURE_RECOGNIZED, lambda e: received.append(e))

        ge = GestureEvent(
            gesture=GestureType.THUMBS_UP,
            hand=None,
            position=(0.6, 0.4),
            confidence=0.85,
            timestamp_ms=int(time.time() * 1000),
        )
        executor.process_events([ge])

        self.assertEqual(len(received), 1)
        data = received[0].data
        self.assertEqual(data["gesture"], "Thumb_Up")
        self.assertEqual(data["action"], "confirm")
        self.assertAlmostEqual(data["position"][0], 0.6, places=1)

    def test_all_gestures_emitted_on_bus(self):
        bus = EventBus()
        engine = GestureEngine({"dwell_time_ms": 0})
        executor = GestureActionExecutor(bus, engine)

        received = []
        bus.subscribe(EventType.GESTURE_RECOGNIZED, lambda e: received.append(e))

        for gt in [GestureType.FIST, GestureType.OPEN_PALM, GestureType.POINT,
                   GestureType.THUMBS_UP, GestureType.THUMB_DOWN]:
            ge = GestureEvent(
                gesture=gt, hand=None, position=(0.5, 0.5),
                confidence=0.9, timestamp_ms=int(time.time() * 1000),
            )
            executor.process_events([ge])

        actions_received = [e.data["action"] for e in received]
        self.assertIn("cancel", actions_received)
        self.assertIn("toggle_ui", actions_received)
        self.assertIn("move_cursor", actions_received)
        self.assertIn("confirm", actions_received)


if __name__ == "__main__":
    unittest.main()
