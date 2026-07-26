"""
Hand Perception Plugin — MediaPipe GestureRecognizer as a plugin.

Reads frames from FrameBroker, runs gesture recognition,
writes results to PerceptionResult. Never touches EventBus directly.

Data flow:
    FrameBroker → HandPerceptionPlugin → PerceptionResult → VisionEventAdapter → EventBus
"""

import logging
import threading
import time
import cv2
import mediapipe as mp
import numpy as np

from aether.core.plugin import PluginBase
from aether.vision import DetectedHand, PerceptionResult
from aether.core.frame_broker import FrameBroker
from aether.core.profiler import profiler
from aether.core.adaptive_scheduler import adaptive_scheduler

logger = logging.getLogger("Aether.HandPerception")


class HandPerceptionPlugin(PluginBase):
    """MediaPipe GestureRecognizer running as a daemon plugin.

    Consumes frames from FrameBroker, runs gesture recognition,
    writes results to PerceptionResult. Never publishes Events directly.

    Data flow:
        FrameBroker → HandPerceptionPlugin → PerceptionResult

    Uses AdaptiveScheduler for dynamic rate control based on:
    - CPU load / main thread tick budget
    - Frame age
    - End-to-end latency
    """

    name = "hand_perception"

    def __init__(self, model_path="models/gesture_recognizer.task", config=None):
        super().__init__()
        self.model_path = model_path
        self.config = config or {}
        self._broker = None
        self._perception = None
        self._running = False
        self._thread = None
        self._frame_event = None
        self._last_process_time = 0.0

    def initialize(self, container):
        self._broker = container.resolve("frame_broker")
        self._perception = container.resolve("perception_result")

        self._frame_event = self._broker.register_consumer("hand_perception")

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def shutdown(self):
        self._running = False
        if self._frame_event:
            self._frame_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._broker:
            self._broker.unregister_consumer("hand_perception")

    def _run(self):
        try:
            base_options = mp.tasks.BaseOptions(model_asset_path=self.model_path)
            options = mp.tasks.vision.GestureRecognizerOptions(
                base_options=base_options,
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_hands=self.config.get("num_hands", 2),
                min_hand_detection_confidence=self.config.get("min_hand_detection_confidence", 0.5),
                min_hand_presence_confidence=self.config.get("min_hand_presence_confidence", 0.5),
                min_tracking_confidence=self.config.get("min_tracking_confidence", 0.5),
            )

            recognizer = mp.tasks.vision.GestureRecognizer.create_from_options(options)

            while self._running:
                self._frame_event.wait(timeout=1.0)
                if not self._running:
                    break
                self._frame_event.clear()

                # Adaptive scheduling: get recommended interval and skip decision
                mp_interval = adaptive_scheduler.get_mediapipe_interval()
                should_skip = adaptive_scheduler.should_skip_mediapipe()

                # Time-based throttle with adaptive interval
                now = time.perf_counter()
                if now - self._last_process_time < mp_interval:
                    continue
                self._last_process_time = now

                if should_skip:
                    continue

                frame = self._broker.get_frame()
                if frame is None:
                    continue

                t0 = time.perf_counter()

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                timestamp = int(time.time() * 1000)

                result = recognizer.recognize_for_video(mp_image, timestamp)

                hands = []
                if result.hand_landmarks:
                    for idx, landmarks in enumerate(result.hand_landmarks):
                        label = "Unknown"
                        if result.handedness and idx < len(result.handedness):
                            label = result.handedness[idx][0].category_name

                        pts = [{"x": lm.x, "y": lm.y, "z": lm.z} for lm in landmarks]

                        gesture_name = "Unknown"
                        gesture_score = 0.0
                        if result.gestures and idx < len(result.gestures):
                            top = result.gestures[idx][0]
                            gesture_name = top.category_name
                            gesture_score = top.score

                        hands.append(DetectedHand(
                            label=label,
                            landmarks=pts,
                            gesture=gesture_name,
                            gesture_score=gesture_score,
                        ))

                # Write to PerceptionResult — never to EventBus
                self._perception.update_hands(hands, frame_id=self._broker.get_frame_id())

                ms = (time.perf_counter() - t0) * 1000.0
                profiler._record_stage("mediapipe", ms)

        except Exception as e:
            logger.error("HandPerceptionPlugin error: %s", e)


class FrameBrokerPlugin(PluginBase):
    """Provides FrameBroker as a shared service.

    FrameBroker distributes frames to perception plugins.
    CameraPlugin writes frames here; YOLO/MediaPipe read from here.
    """

    name = "frame_broker"

    def __init__(self):
        self._broker = None

    def initialize(self, container):
        event_bus = container.resolve("event_bus") if container.has("event_bus") else None
        self._broker = FrameBroker(event_bus=event_bus)
        container.register_instance("frame_broker", self._broker)
        self._broker.set_event_bus(event_bus)

    def shutdown(self):
        pass