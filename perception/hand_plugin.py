import threading
import time
import logging
import cv2
import numpy as np
import mediapipe as mp

from core.frame_broker import FrameBroker
from core.event_bus import EventBus, EventType


class HandPerceptionPlugin(threading.Thread):
    """Processes frames using MediaPipe GestureRecognizer.

    Runs as a daemon thread. Emits HAND_DETECTED events on the EventBus with
    hand landmarks AND native gesture classification from the model.
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
            options = mp.tasks.vision.GestureRecognizerOptions(
                base_options=base_options,
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_hands=self.config.get("num_hands", 2),
                min_hand_detection_confidence=self.config.get("min_hand_detection_confidence", 0.5),
                min_hand_presence_confidence=self.config.get("min_hand_presence_confidence", 0.5),
                min_tracking_confidence=self.config.get("min_tracking_confidence", 0.5),
            )

            with mp.tasks.vision.GestureRecognizer.create_from_options(options) as recognizer:
                self.logger.info(f"Gesture recognizer ready (model={self.model_path})")

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

                    result = recognizer.recognize_for_video(mp_image, timestamp)

                    observations = []
                    if result.hand_landmarks:
                        for idx, hand_landmarks in enumerate(result.hand_landmarks):
                            lbl = result.handedness[idx][0].category_name if result.handedness else "Unknown"
                            pts = [{"x": lm.x, "y": lm.y, "z": lm.z} for lm in hand_landmarks]

                            gesture_name = "Unknown"
                            gesture_score = 0.0
                            if result.gestures and idx < len(result.gestures):
                                top_gesture = result.gestures[idx][0]
                                gesture_name = top_gesture.category_name
                                gesture_score = top_gesture.score

                            observations.append({
                                "label": lbl,
                                "landmarks": pts,
                                "gesture": gesture_name,
                                "gesture_score": gesture_score,
                            })

                    self.bus.emit(EventType.HAND_DETECTED, data={"hands": observations}, source="hand_plugin")

        except Exception as e:
            self.logger.error(f"Hand perception error: {e}", exc_info=True)

    def stop(self):
        self._running = False
        self.broker.new_frame_event.set()
        self.join(timeout=2.0)
        self.logger.info("Hand perception plugin stopped")
