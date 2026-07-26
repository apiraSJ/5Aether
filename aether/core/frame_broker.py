"""
FrameBroker — central frame distribution system for the vision pipeline.

Architecture:
    CameraPlugin (thread) -> FrameBroker -> YOLOPlugin / MediaPipePlugin

FrameBroker is the single source of truth for camera frames.
- CameraPlugin writes frames here
- Perception plugins pull frames at their own FPS
- Only frame_id/timestamp metadata is emitted via EventBus
- Frame data never flows through EventBus
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from aether.core.event_bus_v2 import EventBus
from aether.core.profiler import profiler

logger = logging.getLogger("Aether.FrameBroker")


class FrameBroker:
    """Thread-safe frame distribution system.

    CameraPlugin updates frames here. Perception plugins pull frames
    independently at their own rate. Frame data stays in memory.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._frame: Any = None
        self._lock = threading.Lock()
        self._frame_id: int = 0
        self._timestamp: float = 0.0
        self._capture_ts: float = 0.0
        self._event_bus: EventBus | None = event_bus
        self._subscribers: dict[str, float] = {}
        self._consumer_events: dict[str, threading.Event] = {}
        self._last_frame_time: float = 0.0
        self._min_interval: float = 1.0 / 30.0
        self._overwritten_count: int = 0
        self._total_frames: int = 0

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Set EventBus for emitting frame.ready events."""
        self._event_bus = event_bus

    def update_frame(self, frame: Any, capture_ts: float = 0.0) -> None:
        """Store latest frame from camera. Emits frame.ready with metadata only."""
        now = time.time()

        # Rate limit: don't emit faster than 30fps
        if now - self._last_frame_time < self._min_interval:
            return

        with self._lock:
            if self._frame is not None:
                self._overwritten_count += 1
            self._frame = frame
            self._frame_id += 1
            self._timestamp = now
            self._capture_ts = capture_ts if capture_ts > 0 else now
            self._last_frame_time = now
            self._total_frames += 1

        # Notify all consumers that a new frame is available
        for event in self._consumer_events.values():
            event.set()

        # Emit frame.ready with metadata only (no frame data)
        if self._event_bus:
            self._event_bus.publish_now(
                "vision.frame.ready",
                {
                    "frame_id": self._frame_id,
                    "timestamp": self._timestamp,
                    "capture_ts": self._capture_ts,
                },
                source="frame_broker",
            )

        # Report queue metrics to profiler
        profiler.set_queue(
            "frame_broker",
            depth=len(self._consumer_events),
            overwritten=self._overwritten_count,
            total_frames=self._total_frames,
        )

    def get_frame(self) -> Any:
        """Pull latest frame. Safe for concurrent access."""
        with self._lock:
            return self._frame

    def get_frame_id(self) -> int:
        with self._lock:
            return self._frame_id

    def get_timestamp(self) -> float:
        with self._lock:
            return self._timestamp

    def get_capture_ts(self) -> float:
        with self._lock:
            return self._capture_ts

    def register_consumer(self, name: str, desired_fps: float = 30.0) -> threading.Event:
        """Register a perception plugin by name.

        Returns a threading.Event that is set when a new frame is available.
        Plugins wait on this event instead of polling.
        """
        event = threading.Event()
        self._subscribers[name] = desired_fps
        self._consumer_events[name] = event
        logger.debug("Consumer '%s' registered at %s fps", name, desired_fps)
        return event

    def unregister_consumer(self, name: str) -> None:
        self._subscribers.pop(name, None)
        self._consumer_events.pop(name, None)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
