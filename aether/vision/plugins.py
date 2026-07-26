"""Vision pipeline plugins — PerceptionResult, VisionStateBuilder, VisionEventAdapter.

Load order in vision.yaml:
  1. FrameBrokerPlugin    — provides FrameBroker
  2. PerceptionPlugin     — provides PerceptionResult (thread-safe container)
  3. VisionAdapterPlugin  — builds VisionState, publishes Events (worker thread, adaptive Hz)
  4. CameraPlugin         — starts camera, writes to FrameBroker
  5. HandPerceptionPlugin — reads FrameBroker, writes to PerceptionResult
  6. ObjectSpatialPlugin  — reads FrameBroker, writes to PerceptionResult
"""

from __future__ import annotations

import logging
import threading
import time

from aether.core.plugin import PluginBase, PluginMetadata
from aether.vision import PerceptionResult
from aether.vision.event_adapter import VisionEventAdapter
from aether.vision.state_builder import VisionStateBuilder
from aether.vision.tracker import DetectionTracker
from aether.vision.vision_state import DetectedHand
from aether.core.profiler import profiler
from aether.core.adaptive_scheduler import adaptive_scheduler

logger = logging.getLogger("Aether.VisionPlugins")


class PerceptionPlugin(PluginBase):
    """Provides PerceptionResult as a shared service in the DI container.

    PerceptionResult is the thread-safe container that perception plugins
    (YOLO, MediaPipe) write to during each frame.
    """

    name = "perception_result"

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="PerceptionResult", version="1.0", category="vision",
            description="Thread-safe perception results shared between YOLO/MediaPipe and EventBus"
        )

    def initialize(self, container):
        self._perception = PerceptionResult()
        container.register_instance("perception_result", self._perception)
        logger.info("PerceptionResult registered")

    def shutdown(self):
        pass


class VisionAdapterPlugin(PluginBase):
    """Worker thread plugin that builds VisionState and publishes Events at adaptive Hz.

    Runs in its own thread — does NOT block the main tick loop.

    Each iteration:
      1. Reads raw perception data from PerceptionResult (non-blocking lock+copy)
      2. Runs DetectionTracker on objects (assigns persistent IDs)
      3. Builds VisionState via VisionStateBuilder
      4. VisionEventAdapter compares snapshots and emits Events

    Data flow:
        PerceptionResult → DetectionTracker → VisionStateBuilder → VisionState → VisionEventAdapter → EventBus

    Uses AdaptiveScheduler for dynamic rate control based on:
    - Main thread tick budget usage
    - Frame age (data freshness)
    - End-to-end latency
    """

    name = "vision_adapter"

    def __init__(self):
        self._adapter: VisionEventAdapter | None = None
        self._builder: VisionStateBuilder | None = None
        self._tracker: DetectionTracker | None = None
        self._event_bus = None
        self._perception = None
        self._broker = None
        self._frame_count: int = 0
        self._last_fps_time: float = 0.0
        self._fps: float = 0.0
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._last_process_time = 0.0

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="VisionAdapter", version="3.0", category="vision",
            description="Builds VisionState from PerceptionResult on worker thread (adaptive Hz), publishes Events to EventBus"
        )

    def initialize(self, container):
        self._event_bus = container.resolve("event_bus")
        self._perception = container.resolve("perception_result")
        self._broker = container.resolve("frame_broker")
        self._adapter = VisionEventAdapter(self._event_bus)
        self._builder = VisionStateBuilder()
        self._tracker = DetectionTracker(iou_threshold=0.3, max_lost=10)
        self._last_fps_time = time.time()

        self._running = True
        self._thread = threading.Thread(target=self._run, name="vision-adapter", daemon=True)
        self._thread.start()
        logger.info("VisionAdapterPlugin started (worker thread, adaptive Hz)")

    def _run(self):
        """Worker loop — runs at adaptive Hz in its own thread."""
        while self._running:
            # Check skip BEFORE processing — if skipped, do NOT call _process_frame
            should_skip = adaptive_scheduler.should_skip_vision()
            if should_skip:
                time.sleep(0.005)
                continue

            frame_start = time.perf_counter()

            try:
                self._process_frame()
            except Exception:
                logger.exception("VisionAdapterPlugin frame error")

            # Sleep to maintain target rate from adaptive scheduler
            vision_interval = adaptive_scheduler.get_vision_interval()
            elapsed = time.perf_counter() - frame_start
            sleep_time = vision_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _process_frame(self):
        """Single frame processing — reads latest data, builds state, emits events."""
        if not self._adapter or not self._builder or not self._perception:
            return

        t0 = time.perf_counter()
        now = time.time()

        # E2E latency from FrameBroker capture timestamp (capture → now)
        if self._broker:
            capture_ts = self._broker.get_capture_ts()
            if capture_ts > 0:
                profiler.record_render(capture_ts)

        # Calculate FPS
        self._frame_count += 1
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._last_fps_time = now

        # 1. Read raw perception data (non-blocking — lock + copy)
        raw_objects = self._perception.get_objects()
        hands = self._perception.get_hands()

        # 2. Run tracker on objects (assigns persistent IDs)
        tracked_objects = self._tracker.update(raw_objects)

        # 3. Build VisionState via builder
        frame_id = self._perception.get_frame_id()
        self._builder.begin_frame(frame_id, now)
        self._builder.update_objects(tracked_objects)
        self._builder.update_hands(hands)

        # Extract cursor from hand landmarks
        if hands:
            hand = hands[0]
            if hand.landmarks:
                wrist = hand.landmarks[0]
                self._builder.update_cursor(wrist.get("x", 0.0), wrist.get("y", 0.0))

            # Extract gesture
            for hand in hands:
                if hand.gesture != "Unknown" and hand.gesture_score >= 0.5:
                    self._builder.update_gesture(hand.gesture, hand.gesture_score)
                    break
        else:
            self._builder.update_gesture(None, 0.0)

        self._builder.update_fps(self._fps)

        # 4. Build and publish
        state = self._builder.build()
        self._adapter.update(state)

        ms = (time.perf_counter() - t0) * 1000.0
        profiler._record_stage("vision_adapter", ms)

    def shutdown(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._adapter:
            self._adapter.reset()
        if self._tracker:
            self._tracker.reset()
        logger.info("VisionAdapterPlugin shutdown")