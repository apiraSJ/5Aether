"""Vision pipeline — perception results, vision state, and event adapter.

This module defines the clean boundary between perception (YOLO, MediaPipe)
and the rest of the system.

Data flow:
    Camera → FrameBroker → YOLO/MediaPipe → PerceptionResult → VisionStateBuilder → VisionState → VisionEventAdapter → EventBus

Key types:
    PerceptionResult:  thread-safe container for raw perception data
    VisionState:       immutable snapshot of all perception data per frame
    VisionStateBuilder: builds VisionState from PerceptionResult
    VisionEventAdapter: compares VisionState snapshots, emits diff events
    DetectionTracker:  assigns persistent IDs to detected objects
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

# Re-export vision state types
from aether.vision.vision_state import (
    DetectedHand,
    DetectedObject,
    TrackedObject,
    VisionState,
)

logger = logging.getLogger("Aether.Vision")


class PerceptionResult:
    """Thread-safe shared state between perception plugins and VisionEventAdapter.

    Perception plugins WRITE here (update_objects, update_hands).
    VisionAdapterPlugin READS here and builds VisionState.

    No EventBus dependency — pure data container.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._objects: list[DetectedObject] = []
        self._hands: list[DetectedHand] = []
        self._frame_id: int = 0
        self._timestamp: float = 0.0

    def update_objects(self, objects: list[DetectedObject], frame_id: int = 0) -> None:
        """Replace object list from YOLO detection."""
        with self._lock:
            self._objects = objects
            self._frame_id = frame_id
            self._timestamp = time.time()

    def update_hands(self, hands: list[DetectedHand], frame_id: int = 0) -> None:
        """Replace hand list from MediaPipe."""
        with self._lock:
            self._hands = hands
            self._frame_id = frame_id
            self._timestamp = time.time()

    def get_objects(self) -> list[DetectedObject]:
        """Snapshot of current objects."""
        with self._lock:
            return list(self._objects)

    def get_hands(self) -> list[DetectedHand]:
        """Snapshot of current hands."""
        with self._lock:
            return list(self._hands)

    def get_frame_id(self) -> int:
        with self._lock:
            return self._frame_id

    def get_timestamp(self) -> float:
        with self._lock:
            return self._timestamp
