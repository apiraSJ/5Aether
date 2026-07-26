"""VisionEventAdapter — compares VisionState snapshots, publishes Events to EventBus.

This is the ONLY component that bridges the Vision Pipeline to the EventBus.
Perception plugins never touch EventBus directly.

Data flow:
    VisionState → VisionEventAdapter → EventBus → OverlayController / AI / Memory / Logger

Responsibilities:
  - Diff tracked objects to emit DETECTED / UPDATED / LOST events
  - Emit cursor.moved events from hand landmarks
  - Emit gesture lifecycle events (STARTED / HOLDING / ENDED)
  - Emit frame.ready events with frame_id (never frame data)
"""

from __future__ import annotations

import logging
import time

from aether.core.event_bus_v2 import EventBus
from aether.vision.vision_state import VisionState

logger = logging.getLogger("Aether.VisionEventAdapter")


class VisionEventAdapter:
    """Bridges VisionState snapshots to EventBus. One-way data flow.

    Subscribes to nothing. Called by VisionAdapterPlugin with a new
    VisionState each tick. Compares against previous snapshot to emit
    diff-based events.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

        # Previous state for diffing
        self._prev_object_ids: set[int] = set()
        self._prev_hand_labels: set[str] = set()
        self._prev_hand_gesture: str = "Unknown"
        self._prev_gesture: str | None = None
        self._prev_gesture_start: float = 0.0
        self._prev_cursor_x: float = 0.0
        self._prev_cursor_y: float = 0.0

    def update(self, state: VisionState) -> None:
        """Called each tick with a new VisionState snapshot.

        Compares state against previous snapshot and emits diff-based events.
        """
        self._emit_frame_ready(state)
        self._emit_object_events(state)
        self._emit_hand_events(state)
        self._emit_cursor_events(state)
        self._emit_gesture_events(state)

    def _emit_frame_ready(self, state: VisionState) -> None:
        """Publish frame.ready with frame_id (never frame data)."""
        self._event_bus.publish_now(
            "vision.frame.ready",
            {"frame_id": state.frame_id, "timestamp": state.timestamp},
            source="vision_adapter",
        )

    def _emit_object_events(self, state: VisionState) -> None:
        """Diff tracked object IDs: emit DETECTED / UPDATED / LOST."""
        current_ids = {obj.id for obj in state.objects}
        current_by_id = {obj.id: obj for obj in state.objects}

        # Objects that appeared (new IDs)
        new_ids = current_ids - self._prev_object_ids
        if new_ids:
            self._event_bus.publish_now(
                "vision.object.detected",
                {
                    "objects": [
                        {
                            "id": obj.id,
                            "label": obj.label,
                            "conf": obj.confidence,
                            "box": obj.box,
                            "position": obj.position,
                        }
                        for obj in state.objects
                        if obj.id in new_ids
                    ]
                },
                source="vision_adapter",
            )

        # Objects that disappeared (lost IDs)
        lost_ids = self._prev_object_ids - current_ids
        if lost_ids:
            for obj_id in lost_ids:
                self._event_bus.publish_now(
                    "vision.object.lost",
                    {"id": obj_id},
                    source="vision_adapter",
                )

        # Objects still tracked (continuous update)
        tracked_ids = current_ids & self._prev_object_ids
        if tracked_ids:
            self._event_bus.publish_now(
                "vision.object.tracked",
                {
                    "objects": [
                        {
                            "id": obj.id,
                            "label": obj.label,
                            "conf": obj.confidence,
                            "box": obj.box,
                            "position": obj.position,
                        }
                        for obj in state.objects
                        if obj.id in tracked_ids
                    ]
                },
                source="vision_adapter",
            )

        self._prev_object_ids = current_ids

    def _emit_hand_events(self, state: VisionState) -> None:
        """Emit hand detection events — only emit updated if data changed."""
        current_labels = {h.label for h in state.hands}

        if state.hands:
            if not self._prev_hand_labels:
                # New detection
                self._event_bus.publish_now(
                    "vision.hand.detected",
                    {
                        "hands": [
                            {
                                "label": h.label,
                                "landmarks": h.landmarks,
                                "gesture": h.gesture,
                                "gesture_score": h.gesture_score,
                            }
                            for h in state.hands
                        ]
                    },
                    source="vision_adapter",
                )
            else:
                # Check if hand data actually changed (gesture or landmark shift)
                hand_changed = False
                for h in state.hands:
                    if h.gesture != self._prev_hand_gesture:
                        hand_changed = True
                        break
                if hand_changed:
                    self._event_bus.publish_now(
                        "vision.hand.updated",
                        {
                            "hands": [
                                {
                                    "label": h.label,
                                    "landmarks": h.landmarks,
                                    "gesture": h.gesture,
                                    "gesture_score": h.gesture_score,
                                }
                                for h in state.hands
                            ]
                        },
                        source="vision_adapter",
                    )
                    if state.hands:
                        self._prev_hand_gesture = state.hands[0].gesture
        else:
            for label in self._prev_hand_labels:
                self._event_bus.publish_now(
                    "vision.hand.lost",
                    {"label": label},
                    source="vision_adapter",
                )

        self._prev_hand_labels = current_labels

    def _emit_cursor_events(self, state: VisionState) -> None:
        """Emit cursor.moved if position changed."""
        if (state.cursor_x != self._prev_cursor_x or
                state.cursor_y != self._prev_cursor_y):
            self._event_bus.publish_now(
                "vision.cursor.moved",
                {"x": state.cursor_x, "y": state.cursor_y},
                source="vision_adapter",
            )
            self._prev_cursor_x = state.cursor_x
            self._prev_cursor_y = state.cursor_y

    def _emit_gesture_events(self, state: VisionState) -> None:
        """Emit gesture lifecycle: STARTED / HOLDING / ENDED."""
        gesture = state.gesture

        if gesture and gesture != "Unknown" and state.gesture_conf >= 0.5:
            if gesture != self._prev_gesture:
                # New gesture started
                self._event_bus.publish_now(
                    "vision.gesture.started",
                    {
                        "gesture": gesture,
                        "confidence": state.gesture_conf,
                    },
                    source="vision_adapter",
                )
                self._prev_gesture_start = time.time()
                self._prev_gesture = gesture
            else:
                # Gesture still holding
                duration = time.time() - self._prev_gesture_start
                self._event_bus.publish_now(
                    "vision.gesture.holding",
                    {
                        "gesture": gesture,
                        "confidence": state.gesture_conf,
                        "duration": duration,
                    },
                    source="vision_adapter",
                )
        elif self._prev_gesture is not None and self._prev_gesture != "Unknown":
            # Gesture ended
            self._event_bus.publish_now(
                "vision.gesture.ended",
                {"gesture": self._prev_gesture},
                source="vision_adapter",
            )
            self._prev_gesture = None

    def reset(self) -> None:
        """Clear all previous state."""
        self._prev_object_ids.clear()
        self._prev_hand_labels.clear()
        self._prev_hand_gesture = "Unknown"
        self._prev_gesture = None
        self._prev_gesture_start = 0.0
        self._prev_cursor_x = 0.0
        self._prev_cursor_y = 0.0
