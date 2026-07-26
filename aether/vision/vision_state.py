"""VisionState — single immutable snapshot of all perception data per frame.

All perception plugins (YOLO, MediaPipe, Cursor) write their results into
a VisionStateBuilder during each frame. The builder produces a VisionState
snapshot that VisionEventAdapter compares against the previous snapshot
to emit diff-based events to EventBus.

Data flow:
    PerceptionResult → VisionStateBuilder → VisionState → VisionEventAdapter → EventBus
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TrackedObject:
    """A detected object with persistent tracking across frames.

    The tracker assigns stable IDs so that:
        Bottle #15 seen in frame 100 and frame 101 is the same object
        Spatial Memory and AI can reason about object history.
    """

    id: int = 0
    label: str = ""
    confidence: float = 0.0
    box: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    age: int = 0
    last_seen: float = 0.0


@dataclass
class DetectedObject:
    """A single detected object with spatial info (raw from perception)."""

    name: str = ""
    confidence: float = 0.0
    box: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    distance_z: float = 0.0


@dataclass
class DetectedHand:
    """A detected hand with landmarks and gesture."""

    label: str = "Unknown"
    landmarks: List[dict] = field(default_factory=list)
    gesture: str = "Unknown"
    gesture_score: float = 0.0


@dataclass
class VisionState:
    """Immutable snapshot of all perception data for a single frame.

    Created by VisionStateBuilder.build(). Compared by VisionEventAdapter
    to emit diff-based events to EventBus.

    Fields:
        frame_id:     monotonically increasing frame counter
        timestamp:    time.time() when snapshot was created
        objects:      tracked objects from YOLO + tracker
        hands:        detected hands from MediaPipe
        cursor_x/y:   cursor position from hand landmarks
        gesture:      current gesture name (or None)
        gesture_conf: gesture confidence score
        fps:          current frame rate
    """

    frame_id: int = 0
    timestamp: float = 0.0

    objects: List[TrackedObject] = field(default_factory=list)
    hands: List[DetectedHand] = field(default_factory=list)

    cursor_x: float = 0.0
    cursor_y: float = 0.0

    gesture: Optional[str] = None
    gesture_conf: float = 0.0

    fps: float = 0.0
