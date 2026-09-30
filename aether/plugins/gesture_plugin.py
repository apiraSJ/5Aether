"""GesturePlugin — routes hand gestures through the unified input pipeline.

Architecture:
    MediaPipe Hand → HandController → CursorMapper → InputRouter → InteractionController
                                                                     |
                                                            CommandBus / EventBus

This plugin replaces the old GestureInputPlugin which hardcoded gesture→command.
Now gestures flow through the same pipeline as mouse/voice input.

Config-driven:
    gesture.yaml maps gestures to commands.
    No hardcoded gesture logic in this plugin.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

from aether.core.plugin import TickablePlugin, PluginMetadata
from aether.core.service_container import ServiceContainer
from aether.interaction.hand_controller import HandController, HandGesture
from aether.interaction.gestures import Gesture
from aether.interaction.cursor_mapper import CursorMapper, MapperConfig

if TYPE_CHECKING:
    pass

logger = logging.getLogger("Aether.GesturePlugin")


class GesturePlugin(TickablePlugin):
    """Routes hand gestures through the unified input pipeline.

    Flow:
        MediaPipe hand events → HandController → CursorMapper → InputRouter

    This plugin:
    1. Subscribes to vision.hand.detected events
    2. Passes landmarks to HandController for gesture recognition
    3. Maps position through CursorMapper for stability
    4. Routes to InputRouter (same as mouse)
    """

    name = "gesture_plugin"

    def __init__(self) -> None:
        self._container: Optional[ServiceContainer] = None
        self._event_bus = None
        self._hand_controller: Optional[HandController] = None
        self._cursor_mapper: Optional[CursorMapper] = None
        self._input_router = None
        self._running = False
        self._was_pinching: dict[str, bool] = {}

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Gesture", version="2.0", category="input",
            description="Hand gesture input via unified pipeline"
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._event_bus = container.resolve("event_bus")

        # Load gesture config
        gesture_config = self._load_gesture_config()

        # Create HandController (no knowledge of panels/UI)
        self._hand_controller = HandController(gesture_config.get("settings", {}))
        self._hand_controller.load_gesture_config(gesture_config.get("gestures", {}))

        # Create CursorMapper (smooth + anchor)
        mapper_config = MapperConfig(
            ema_alpha=0.3,
            dead_zone=2.0,
            sensitivity=1.0,
            pinch_anchor_smoothing=0.1,
        )
        self._cursor_mapper = CursorMapper(mapper_config)

        logger.info("GesturePlugin initialized (%d gestures loaded)",
                     len(gesture_config.get("gestures", {})))

    def start(self) -> None:
        if not self._container:
            raise RuntimeError("GesturePlugin requires ServiceContainer")

        if not self._container.has("input_router"):
            raise RuntimeError(
                "GesturePlugin requires InputRouter — InteractionPlugin must start first. "
                "Verify plugin order in config: interaction_plugin BEFORE gesture_plugin."
            )

        self._input_router = self._container.resolve("input_router")

        # Subscribe to hand detection events
        if self._event_bus:
            self._event_bus.subscribe("vision.hand.detected", self._on_hand_detected)

        self._running = True
        logger.info("GesturePlugin started")

    def update(self, dt: float) -> None:
        """Called each frame. GesturePlugin is event-driven, so this is minimal.

        Could be used for periodic cooldown cleanup or state validation in the future.
        """
        pass

    def stop(self) -> None:
        self._running = False
        if self._event_bus:
            self._event_bus.unsubscribe("vision.hand.detected", self._on_hand_detected)
        logger.info("GesturePlugin stopped")

    def _on_hand_detected(self, event) -> None:
        """Process hand detection event through unified pipeline."""
        if not self._running or not self._hand_controller or not self._input_router:
            return

        hands = event.payload.get("hands", [])

        for hand in hands:
            landmarks = hand.get("landmarks", [])
            gesture_name = hand.get("gesture", "Unknown")
            confidence = hand.get("gesture_score", 0.0)
            label = hand.get("label", "Right")

            if not landmarks or len(landmarks) < 21:
                continue

            # Process through HandController → HandInputEvent
            hand_event = self._hand_controller.process_hand_landmarks(
                landmarks=landmarks,
                gesture_name=gesture_name,
                confidence=confidence,
                hand_label=label,
            )

            if hand_event is None:
                continue

            # Map position through CursorMapper for stability
            is_pinching = hand_event.gesture == HandGesture.PINCH
            screen_x, screen_y = self._cursor_mapper.process(
                hand_event.position_x,
                hand_event.position_y,
                is_pinching=is_pinching,
            )

            # Route through InputRouter (same as mouse!)
            self._route_to_input_router(hand_event, screen_x, screen_y)

    def _route_to_input_router(
        self,
        hand_event,
        screen_x: float,
        screen_y: float,
    ) -> None:
        """Route HandInputEvent through InputRouter.

        This is where hand becomes just another input device.
        """
        router = self._input_router

        # Always route cursor movement
        router.on_hand_move(screen_x, screen_y)

        # Handle pinch state transitions
        label = hand_event.hand_label
        is_pinching = hand_event.gesture == HandGesture.PINCH
        was_pinching = self._was_pinching.get(label, False)

        if is_pinching and not was_pinching:
            # Pinch started → equivalent to mouse press
            router.on_hand_pinch_start(screen_x, screen_y)
            logger.debug("Pinch start: (%.0f, %.0f)", screen_x, screen_y)

        elif not is_pinching and was_pinching:
            # Pinch ended → equivalent to mouse release
            router.on_hand_pinch_end(screen_x, screen_y)
            logger.debug("Pinch end: (%.0f, %.0f)", screen_x, screen_y)

        self._was_pinching[label] = is_pinching

        # Handle non-pinch gesture commands (via CommandBus)
        if hand_event.gesture not in (HandGesture.NONE, HandGesture.PINCH):
            self._handle_gesture_command(hand_event)

    def _handle_gesture_command(self, hand_event) -> None:
        """Map gesture to command and dispatch through CommandBus."""
        gesture_enum = hand_event.gesture_enum
        command_name = self._hand_controller.get_gesture_command_by_enum(gesture_enum)

        if command_name and self._container and self._container.has("command_bus"):
            command_bus = self._container.resolve("command_bus")
            from aether.core.command import Command
            cmd = Command(
                name=command_name,
                source="gesture",
                params={
                    "gesture": gesture_enum.value,  # Use enum value, not raw string
                    "hand": hand_event.hand_label,
                    "confidence": hand_event.confidence,
                },
            )
            command_bus.dispatch(cmd)
            logger.debug("Gesture command: %s → %s", gesture_enum.value, command_name)

    def _load_gesture_config(self) -> dict:
        """Load gesture configuration from config/gesture.yaml."""
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/gesture.yaml")
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except (ImportError, FileNotFoundError):
            logger.warning("gesture.yaml not found, using defaults")

        return {
            "gestures": {
                "pinch": {"command": "interaction.cursor.click", "enabled": True, "cooldown": 300, "confidence": 0.8},
                "open_palm": {"command": "interaction.cursor.enable", "enabled": True, "cooldown": 500, "confidence": 0.7},
                "fist": {"command": "interaction.mode.reset", "enabled": True, "cooldown": 500, "confidence": 0.7},
            },
            "settings": {"enabled": True, "preferred_hand": "right", "global_confidence_threshold": 0.5},
        }
