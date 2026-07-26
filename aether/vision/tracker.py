"""DetectionTracker — IoU-based object tracking across frames.

Assigns persistent IDs to YOLO detections so that:
    Bottle #15 seen in frame 100 and frame 101 is the same object.
    Spatial Memory and AI can reason about object history.

Data flow:
    YOLO raw detections → DetectionTracker.update() → list[TrackedObject]

Usage:
    tracker = DetectionTracker(iou_threshold=0.3, max_lost=10)
    tracked = tracker.update(raw_detections)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List

from .vision_state import DetectedObject, TrackedObject


def _compute_iou(box_a: list[int], box_b: list[int]) -> float:
    """Compute Intersection over Union between two [x1, y1, x2, y2] boxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    area_a = max(1, (box_a[2] - box_a[0]) * (box_a[3] - box_a[1]))
    area_b = max(1, (box_b[2] - box_b[0]) * (box_b[3] - box_b[1]))
    union = area_a + area_b - intersection

    return intersection / union if union > 0 else 0.0


class DetectionTracker:
    """IoU-based tracker that assigns persistent IDs to detected objects.

    Each frame:
        1. Match new detections to existing tracked objects using IoU
        2. Create new tracked objects for unmatched detections
        3. Increment age for unmatched existing objects
        4. Remove objects that exceed max_lost frames

    Args:
        iou_threshold: minimum IoU to consider a match (default 0.3)
        max_lost:      frames before a lost object is removed (default 10)
    """

    def __init__(self, iou_threshold: float = 0.3, max_lost: int = 10) -> None:
        self._iou_threshold = iou_threshold
        self._max_lost = max_lost
        self._tracked: list[TrackedObject] = []
        self._next_id: int = 1

    def update(self, detections: list[DetectedObject]) -> list[TrackedObject]:
        """Match new detections to existing tracks, return updated list.

        Args:
            detections: raw YOLO detections for this frame

        Returns:
            list of TrackedObject with persistent IDs
        """
        now = time.time()

        # Mark all existing tracks as not-yet-matched
        matched_old: list[TrackedObject] = []
        unmatched_old: list[TrackedObject] = list(self._tracked)

        # Match new detections to existing tracks (greedy IoU)
        for det in detections:
            best_iou = 0.0
            best_track = None
            for track in unmatched_old:
                if track.label != det.name:
                    continue
                iou = _compute_iou(track.box, det.box)
                if iou > best_iou:
                    best_iou = iou
                    best_track = track

            if best_track is not None and best_iou >= self._iou_threshold:
                # Update existing track
                best_track.box = list(det.box)
                best_track.confidence = det.confidence
                best_track.position = [0.0, 0.0, det.distance_z]
                best_track.age += 1
                best_track.last_seen = now
                matched_old.append(best_track)
                unmatched_old.remove(best_track)
            else:
                # New object — assign a new ID
                tracked = TrackedObject(
                    id=self._next_id,
                    label=det.name,
                    confidence=det.confidence,
                    box=list(det.box),
                    position=[0.0, 0.0, det.distance_z],
                    age=1,
                    last_seen=now,
                )
                self._next_id += 1
                matched_old.append(tracked)

        # Increment age for unmatched old tracks
        for track in unmatched_old:
            track.age += 1

        # Keep tracks that haven't exceeded max_lost
        kept = [t for t in matched_old if t.age - (t.age - 1) <= self._max_lost]
        # Also keep unmatched tracks if they're still within max_lost
        kept.extend(
            t for t in unmatched_old
            if t.age <= self._max_lost
        )

        self._tracked = kept
        return list(self._tracked)

    def reset(self) -> None:
        """Clear all tracked objects."""
        self._tracked.clear()
        self._next_id = 1

    @property
    def tracked_count(self) -> int:
        """Number of currently tracked objects."""
        return len(self._tracked)
