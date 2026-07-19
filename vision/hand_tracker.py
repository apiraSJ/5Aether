import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class HandLandmark:
    x: float
    y: float
    z: float


@dataclass
class HandData:
    landmarks: List[HandLandmark]
    world_landmarks: List[HandLandmark]
    handedness: str
    confidence: float
    bounding_box: Tuple[int, int, int, int]


@dataclass
class HandResults:
    hands: List[HandData]
    timestamp_ms: int


class HandTracker:
    def __init__(self, config: dict = None):
        self.logger = logging.getLogger("Aether.HandTracker")
        self.config = config or {}
        self.model_path = self.config.get("model_path", "models/hand_landmarker.task")
        self.num_hands = self.config.get("num_hands", 2)
        self.min_detection_confidence = self.config.get("min_detection_confidence", 0.7)
        self.min_tracking_confidence = self.config.get("min_tracking_confidence", 0.5)
        self._detector = None
        self._initialized = False

    def initialize(self):
        try:
            import mediapipe as mp
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision

            base_options = python.BaseOptions(model_asset_path=self.model_path)
            options = vision.HandLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.VIDEO,
                num_hands=self.num_hands,
                min_hand_detection_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence,
            )
            self._detector = vision.HandLandmarker.create_from_options(options)
            self._initialized = True
            self.logger.info("MediaPipe Hand Landmarker initialized")
        except ImportError:
            self.logger.warning("MediaPipe not installed. Hand tracking disabled.")
        except Exception as e:
            self.logger.error(f"Failed to initialize HandLandmarker: {e}")

    def process(self, frame: np.ndarray, timestamp_ms: int = None) -> Optional[HandResults]:
        if not self._initialized or self._detector is None:
            return None

        try:
            import mediapipe as mp

            if timestamp_ms is None:
                timestamp_ms = int(time.time() * 1000)

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
            mp_result = self._detector.detect_for_video(mp_image, timestamp_ms)

            hands = []
            for i in range(len(mp_result.landmarks)):
                landmarks = [
                    HandLandmark(lm.x, lm.y, lm.z)
                    for lm in mp_result.landmarks[i]
                ]
                world_landmarks = []
                if mp_result.world_landmarks:
                    world_landmarks = [
                        HandLandmark(wm.x, wm.y, wm.z)
                        for wm in mp_result.world_landmarks[i]
                    ]

                handedness = "Unknown"
                if mp_result.handedness and i < len(mp_result.handedness):
                    handedness = mp_result.handedness[i][0].category_name

                bbox = self._compute_bbox(landmarks, frame.shape)
                confidence = 1.0

                hands.append(HandData(
                    landmarks=landmarks,
                    world_landmarks=world_landmarks,
                    handedness=handedness,
                    confidence=confidence,
                    bounding_box=bbox,
                ))

            return HandResults(hands=hands, timestamp_ms=timestamp_ms)

        except Exception as e:
            self.logger.error(f"Hand tracking error: {e}")
            return None

    def _compute_bbox(self, landmarks: List[HandLandmark], frame_shape) -> Tuple[int, int, int, int]:
        h, w = frame_shape[:2]
        xs = [lm.x for lm in landmarks]
        ys = [lm.y for lm in landmarks]
        x1 = int(min(xs) * w)
        y1 = int(min(ys) * h)
        x2 = int(max(xs) * w)
        y2 = int(max(ys) * h)
        return (x1, y1, x2, y2)

    def shutdown(self):
        if self._detector:
            self._detector.close()
            self._detector = None
        self._initialized = False
        self.logger.info("Hand tracker shut down")

    @property
    def is_initialized(self):
        return self._initialized
