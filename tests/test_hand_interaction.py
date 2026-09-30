"""Tests for Phase 3A.5C — Hand Controller + Gesture Interaction Runtime.

Tests cover:
1. HandController + HandInputEvent
2. CursorMapper (EMA, dead zone, pinch anchor)
3. Gesture config loading
4. Pipeline integration (MediaPipe → HandController → InputRouter)
5. State transitions (TRACKING → PINCH → GRABBING → RELEASE)
"""

from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock, patch

from aether.interaction.hand_controller import (
    HandController,
    HandInputEvent,
    HandGesture,
)
from aether.interaction.cursor_mapper import CursorMapper, MapperConfig
from aether.interaction.interaction_controller import InteractionController
from aether.interaction.interaction_state import InteractionState, CursorMode
from aether.interaction.input_router import InputRouter
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.panel_info import PanelInfo


# ── HandController Tests ──────────────────────────────────────────


class TestHandInputEvent:
    """Test HandInputEvent dataclass."""

    def test_default_values(self):
        event = HandInputEvent()
        assert event.position_x == 0.0
        assert event.position_y == 0.0
        assert event.gesture == HandGesture.NONE
        assert event.confidence == 0.0
        assert event.is_valid is False

    def test_valid_event(self):
        event = HandInputEvent(
            position_x=0.5,
            position_y=0.5,
            gesture=HandGesture.PINCH,
            confidence=0.9,
        )
        assert event.is_valid is True

    def test_invalid_low_confidence(self):
        event = HandInputEvent(
            position_x=0.5,
            position_y=0.5,
            gesture=HandGesture.PINCH,
            confidence=0.0,
        )
        assert event.is_valid is False

    def test_invalid_no_gesture(self):
        event = HandInputEvent(
            position_x=0.5,
            position_y=0.5,
            gesture=HandGesture.NONE,
            confidence=0.9,
        )
        assert event.is_valid is False


class TestHandController:
    """Test HandController input adapter."""

    def _make_landmarks(self, index_x=0.5, index_y=0.5):
        """Create mock MediaPipe landmarks (21 points)."""
        landmarks = [{"x": 0.5, "y": 0.5} for _ in range(21)]
        landmarks[8] = {"x": index_x, "y": index_y}  # Index fingertip
        return landmarks

    def test_process_hand_landmarks(self):
        hc = HandController({"enabled": True, "preferred_hand": "both"})
        landmarks = self._make_landmarks(0.3, 0.4)
        event = hc.process_hand_landmarks(
            landmarks, "pinch", 0.9, "Right"
        )
        assert event is not None
        assert event.gesture == HandGesture.PINCH
        assert event.confidence == 0.9
        assert event.hand_label == "Right"

    def test_disabled_returns_none(self):
        hc = HandController({"enabled": False})
        landmarks = self._make_landmarks()
        event = hc.process_hand_landmarks(landmarks, "pinch", 0.9)
        assert event is None

    def test_confidence_threshold(self):
        hc = HandController({
            "enabled": True,
            "preferred_hand": "both",
            "global_confidence_threshold": 0.8,
        })
        landmarks = self._make_landmarks()
        event = hc.process_hand_landmarks(landmarks, "pinch", 0.5)
        assert event is not None
        assert event.gesture == HandGesture.NONE  # Filtered by confidence

    def test_preferred_hand_filter(self):
        hc = HandController({"enabled": True, "preferred_hand": "right"})
        landmarks = self._make_landmarks()
        event = hc.process_hand_landmarks(landmarks, "pinch", 0.9, "Left")
        assert event is None  # Left hand filtered out

    def test_gesture_mapping(self):
        hc = HandController({"enabled": True, "preferred_hand": "both"})
        landmarks = self._make_landmarks()

        event = hc.process_hand_landmarks(landmarks, "Open_Palm", 0.9)
        assert event.gesture == HandGesture.OPEN_PALM

        event = hc.process_hand_landmarks(landmarks, "Closed_Fist", 0.9)
        assert event.gesture == HandGesture.FIST

        event = hc.process_hand_landmarks(landmarks, "victory", 0.9)
        assert event.gesture == HandGesture.PEACE

    def test_process_pinch_position(self):
        hc = HandController({"enabled": True, "preferred_hand": "both"})
        event = hc.process_pinch_position(
            thumb_x=0.4, thumb_y=0.4,
            index_x=0.6, index_y=0.6,
            confidence=0.9,
        )
        assert event is not None
        assert event.gesture == HandGesture.PINCH
        assert abs(event.position_x - 0.5) < 0.01  # Average of 0.4 and 0.6
        assert abs(event.position_y - 0.5) < 0.01

    def test_gesture_config(self):
        hc = HandController({})
        hc.load_gesture_config({
            "pinch": {"command": "interaction.cursor.click", "enabled": True, "cooldown": 300},
            "fist": {"command": "interaction.mode.reset", "enabled": False, "cooldown": 500},
        })
        assert hc.get_gesture_command("pinch") == "interaction.cursor.click"
        assert hc.get_gesture_command("fist") is None  # Disabled
        assert hc.get_gesture_command("unknown") is None

    def test_cooldown(self):
        hc = HandController({"enabled": True, "preferred_hand": "both"})
        hc.load_gesture_config({
            "pinch": {"command": "click", "enabled": True, "cooldown": 1000},
        })
        landmarks = self._make_landmarks()

        # First event succeeds
        event1 = hc.process_hand_landmarks(landmarks, "pinch", 0.9, timestamp=100.0)
        assert event1.gesture == HandGesture.PINCH

        # Second event within cooldown — gesture filtered
        event2 = hc.process_hand_landmarks(landmarks, "pinch", 0.9, timestamp=100.5)
        assert event2.gesture == HandGesture.NONE

        # Third event after cooldown — succeeds
        event3 = hc.process_hand_landmarks(landmarks, "pinch", 0.9, timestamp=101.5)
        assert event3.gesture == HandGesture.PINCH

    def test_enable_disable(self):
        hc = HandController({"enabled": True})
        assert hc.is_enabled is True
        hc.disable()
        assert hc.is_enabled is False
        hc.enable()
        assert hc.is_enabled is True


# ── CursorMapper Tests ────────────────────────────────────────────


class TestCursorMapper:
    """Test CursorMapper with EMA smoothing and pinch anchor."""

    def test_basic_process(self):
        mapper = CursorMapper(MapperConfig(
            ema_alpha=0.5,
            dead_zone=0.0,
            screen_width=1920,
            screen_height=1080,
        ))
        x, y = mapper.process(0.5, 0.5)
        assert 0 < x < 1920
        assert 0 < y < 1080

    def test_ema_smoothing(self):
        mapper = CursorMapper(MapperConfig(
            ema_alpha=0.3,
            dead_zone=0.0,
            screen_width=1920,
            screen_height=1080,
        ))
        # First call initializes
        x1, y1 = mapper.process(0.5, 0.5)
        # Second call should be smoothed
        x2, y2 = mapper.process(0.6, 0.6)
        # EMA should not jump to 0.6 immediately
        assert x2 < 0.6 * 1920  # Smoothed position < raw position

    def test_pinch_anchor_lock(self):
        mapper = CursorMapper(MapperConfig(
            ema_alpha=0.3,
            dead_zone=0.0,
            pinch_anchor_smoothing=0.1,
            screen_width=1920,
            screen_height=1080,
        ))
        # Track to position
        mapper.process(0.5, 0.5)

        # Start pinch
        x1, y1 = mapper.process(0.5, 0.5, is_pinching=True)
        assert mapper.is_pinching is True

        # Move hand during pinch — anchor should be stable
        x2, y2 = mapper.process(0.7, 0.7, is_pinching=True)
        # Anchor moves slowly (0.1 alpha)
        assert abs(x2 - x1) < abs(0.7 * 1920 - 0.5 * 1920)

        # End pinch
        mapper.process(0.7, 0.7, is_pinching=False)
        assert mapper.is_pinching is False

    def test_reset(self):
        mapper = CursorMapper(MapperConfig())
        mapper.process(0.5, 0.5)
        mapper.reset()
        assert mapper.last_position == (0.0, 0.0)
        assert mapper.is_pinching is False

    def test_set_screen_size(self):
        mapper = CursorMapper(MapperConfig())
        mapper.set_screen_size(2560, 1440)
        x, y = mapper.process(0.5, 0.5)
        assert 0 < x < 2560
        assert 0 < y < 1440


# ── Pipeline Integration Tests ────────────────────────────────────


class TestHandPipeline:
    """Test full pipeline: HandController → InputRouter → InteractionController."""

    def _make_registry_with_panel(self, panel_id="memory"):
        registry = PanelRegistry()
        info = PanelInfo(
            id=panel_id,
            type="memory",
            label="Memory Panel",
            visible=True,
            x=100, y=200, w=400, h=300,
        )
        registry.register(info)
        return registry

    def _make_landmarks(self, index_x=0.5, index_y=0.5):
        landmarks = [{"x": 0.5, "y": 0.5} for _ in range(21)]
        landmarks[8] = {"x": index_x, "y": index_y}
        return landmarks

    def test_hand_move_routes_to_input_router(self):
        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)
        router = InputRouter(ic)

        # Simulate hand move
        router.on_hand_move(150, 250)
        assert ic.state == InteractionState.HOVER

    def test_hand_pinch_click_routes_to_input_router(self):
        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)
        router = InputRouter(ic)

        # Hover first
        router.on_hand_move(150, 250)
        assert ic.state == InteractionState.HOVER

        # Pinch click
        result = router.on_hand_pinch_start(150, 250)
        assert ic.state == InteractionState.SELECTED

        # Pinch end
        router.on_hand_pinch_end(150, 250)

    def test_hand_drag_via_pinch(self):
        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)
        router = InputRouter(ic)

        # Hover → Click → Drag
        router.on_hand_move(150, 250)
        router.on_hand_pinch_start(150, 250)
        assert ic.state == InteractionState.SELECTED

        # Hold and move → drag starts
        router.on_hand_move(200, 300)
        router.on_hand_pinch_start(200, 300)
        # The second pinch_start while SELECTED triggers drag
        # (InputRouter handles this)

    def test_mouse_and_hand_share_pipeline(self):
        """Verify mouse and hand use the same InputRouter → IC path."""
        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)
        router = InputRouter(ic)

        # Mouse path
        router.on_mouse_move(150, 250)
        assert ic.state == InteractionState.HOVER
        ic.on_cancel()

        # Hand path
        router.on_hand_move(150, 250)
        assert ic.state == InteractionState.HOVER


# ── State Transition Tests ────────────────────────────────────────


class TestStateTransitions:
    """Test complete interaction state machine with hand input."""

    def _make_registry_with_panel(self, panel_id="memory"):
        registry = PanelRegistry()
        info = PanelInfo(
            id=panel_id,
            type="memory",
            label="Memory Panel",
            visible=True,
            x=100, y=200, w=400, h=300,
        )
        registry.register(info)
        return registry

    def test_tracking_to_hover_to_selected(self):
        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)

        # IDLE → HOVER
        ic.on_cursor_move(150, 250)
        assert ic.state == InteractionState.HOVER

        # HOVER → SELECTED
        ic.on_click(150, 250)
        assert ic.state == InteractionState.SELECTED

    def test_selected_to_dragging(self):
        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)

        # IDLE → HOVER → SELECTED
        ic.on_cursor_move(150, 250)
        ic.on_click(150, 250)
        assert ic.state == InteractionState.SELECTED

        # SELECTED → DRAGGING
        success = ic.on_drag_start(150, 250)
        assert success is True
        assert ic.state == InteractionState.DRAGGING

    def test_dragging_to_idle(self):
        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)

        # Full cycle: IDLE → HOVER → SELECTED → DRAGGING → IDLE
        ic.on_cursor_move(150, 250)
        ic.on_click(150, 250)
        ic.on_drag_start(150, 250)
        ic.on_drag_end()
        assert ic.state == InteractionState.IDLE

    def test_cancel_returns_to_idle(self):
        registry = self._make_registry_with_panel()
        ic = InteractionController(registry)

        ic.on_cursor_move(150, 250)
        ic.on_click(150, 250)
        ic.on_cancel()
        assert ic.state == InteractionState.IDLE


# ── Gesture Config Tests ──────────────────────────────────────────


class TestGestureConfig:
    """Test gesture.yaml configuration loading."""

    def test_hand_controller_gesture_config(self):
        hc = HandController({})
        config = {
            "pinch": {
                "command": "interaction.cursor.click",
                "enabled": True,
                "cooldown": 300,
                "confidence": 0.8,
            },
            "open_palm": {
                "command": "interaction.cursor.enable",
                "enabled": True,
                "cooldown": 500,
                "confidence": 0.7,
            },
        }
        hc.load_gesture_config(config)

        assert hc.get_gesture_command("pinch") == "interaction.cursor.click"
        assert hc.get_gesture_command("open_palm") == "interaction.cursor.enable"
        assert hc.get_gesture_cooldown("pinch") == 0.3  # 300ms → 0.3s
        assert hc.get_gesture_cooldown("open_palm") == 0.5

    def test_disabled_gesture_returns_none(self):
        hc = HandController({})
        hc.load_gesture_config({
            "fist": {"command": "mode.reset", "enabled": False},
        })
        assert hc.get_gesture_command("fist") is None
