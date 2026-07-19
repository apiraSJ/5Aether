import threading
import time
import logging
import cv2
import numpy as np
import mediapipe as mp

from core.frame_broker import FrameBroker
from core.event_bus import EventBus, EventType


class HandPerceptionPlugin(threading.Thread):
    """Processes frames from the FrameBroker using MediaPipe HandLandmarker.

    Runs as a daemon thread. Emits HAND_DETECTED events on the EventBus with
    serialized hand observations: [{"label": str, "landmarks": [{"x","y","z"}]}].
    """

    def __init__(self, broker: FrameBroker, bus: EventBus, model_path: str, config: dict = None):
        super().__init__(daemon=True)
        self.broker = broker
        self.bus = bus
        self.model_path = model_path
        self.config = config or {}
        self.logger = logging.getLogger("Aether.HandPerceptionPlugin")
        self._running = True

    def run(self):
        try:
            base_options = mp.tasks.BaseOptions(model_asset_path=self.model_path)
            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_hands=self.config.get("num_hands", 2),
                min_hand_detection_confidence=self.config.get("min_hand_detection_confidence", 0.5),
                min_tracking_confidence=self.config.get("min_tracking_confidence", 0.5),
            )

            with mp.tasks.vision.HandLandmarker.create_from_options(options) as landmarker:
                self.logger.info("Hand landmarker ready")

                while self._running:
                    self.broker.new_frame_event.wait(timeout=1.0)
                    if not self._running:
                        break

                    frame = self.broker.get_frame()
                    self.broker.clear_event()
                    if frame is None:
                        continue

                    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    timestamp = int(time.time() * 1000)

                    result = landmarker.detect_for_video(mp_image, timestamp)

                    observations = []
                    if result.hand_landmarks:
                        for idx, landmarks in enumerate(result.hand_landmarks):
                            lbl = result.handedness[idx][0].category_name if result.handedness else "Unknown"
                            pts = [{"x": lm.x, "y": lm.y, "z": lm.z} for lm in landmarks]
                            observations.append({"label": lbl, "landmarks": pts})

                    self.bus.emit(EventType.HAND_DETECTED, data={"hands": observations}, source="hand_plugin")

        except Exception as e:
            self.logger.error(f"Hand perception error: {e}")

    def stop(self):
        self._running = False
        self.broker.new_frame_event.set()
        self.join(timeout=2.0)
        self.logger.info("Hand perception plugin stopped")
