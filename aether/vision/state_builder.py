"""VisionStateBuilder — collects perception data during a frame and produces
a VisionState snapshot.

Called by VisionAdapterPlugin during each tick:
    builder.begin_frame(frame_id, timestamp)
    builder.update_objects(objects)
    builder.update_hands(hands)
    builder.update_cursor(x, y)
    builder.update_gesture(name, confidence)
    state = builder.build()

No plugin publishes Events directly. The VisionEventAdapter compares the
built VisionState against the previous snapshot and emits diff-based events.
"""

from __future__ import annotations

from .vision_state import DetectedHand, TrackedObject, VisionState


class VisionStateBuilder:
    """Builds a VisionState snapshot from per-frame perception data.

    Plugins write to this builder during each frame. The build() method
    returns an immutable VisionState that VisionEventAdapter uses to
    compute diffs against the previous frame.
    """

    def __init__(self) -> None:
        self._state: VisionState | None = None

    def begin_frame(self, frame_id: int, timestamp: float) -> None:
        """Start a new frame. Clears previous state."""
        self._state = VisionState(frame_id=frame_id, timestamp=timestamp)

    def update_objects(self, objects: list[TrackedObject]) -> None:
        """Set tracked objects for this frame."""
        if self._state is not None:
            self._state.objects = list(objects)

    def update_hands(self, hands: list[DetectedHand]) -> None:
        """Set detected hands for this frame."""
        if self._state is not None:
            self._state.hands = list(hands)

    def update_cursor(self, x: float, y: float) -> None:
        """Set cursor position for this frame."""
        if self._state is not None:
            self._state.cursor_x = x
            self._state.cursor_y = y

    def update_gesture(self, name: str | None, confidence: float = 0.0) -> None:
        """Set current gesture for this frame."""
        if self._state is not None:
            self._state.gesture = name
            self._state.gesture_conf = confidence

    def update_fps(self, fps: float) -> None:
        """Set current frame rate."""
        if self._state is not None:
            self._state.fps = fps

    def build(self) -> VisionState:
        """Return the built VisionState snapshot."""
        if self._state is None:
            return VisionState()
        return self._state
