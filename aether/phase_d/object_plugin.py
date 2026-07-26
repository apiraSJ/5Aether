"""
Object Spatial Plugin — YOLOv8 + solvePnP as a plugin.

Reads frames from FrameBroker, runs YOLO detection + distance estimation,
writes results to PerceptionResult. Never touches EventBus directly.

Data flow:
    FrameBroker -> ObjectSpatialPlugin -> PerceptionResult -> VisionEventAdapter -> EventBus
"""

import threading
import time
import cv2
import numpy as np
from ultralytics import YOLO

from aether.core.plugin import PluginBase
from aether.vision import DetectedObject, PerceptionResult
from aether.core.profiler import profiler
from aether.core.adaptive_scheduler import adaptive_scheduler


class ObjectSpatialPlugin(PluginBase):
    """YOLOv8 object detection + solvePnP distance estimation.

    Reads frames from FrameBroker, writes results to PerceptionResult.
    Never touches EventBus directly.

    Data flow:
        FrameBroker -> ObjectSpatialPlugin -> PerceptionResult

    Uses AdaptiveScheduler for dynamic rate control based on:
    - CPU load
    - Main thread tick budget
    - Frame age
    """

    name = "object_spatial"

    def __init__(self, model_path="yolov8n.pt", config=None):
        super().__init__()
        self.model_path = model_path
        self.config = config or {}
        self._broker = None
        self._perception = None
        self._running = False
        self._thread = None
        self._frame_event = None
        self._model = None
        self._last_detect_time = 0.0

    def initialize(self, container):
        self._broker = container.resolve("frame_broker")
        self._perception = container.resolve("perception_result")

        self._frame_event = self._broker.register_consumer("object_spatial")

        self._model = YOLO(self.model_path)
        self.conf_threshold = self.config.get("confidence", 0.25)
        self.imgsz = self.config.get("imgsz", 320)

        self.object_3d = np.array([
            [-75.0, 25.0, 0.0],
            [75.0, 25.0, 0.0],
            [75.0, -25.0, 0.0],
            [-75.0, -25.0, 0.0],
        ], dtype=np.float32)

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
            self._broker.unregister_consumer("object_spatial")

    def _run(self):
        while self._running:
            self._frame_event.wait(timeout=1.0)
            if not self._running:
                break
            self._frame_event.clear()

            # Adaptive scheduling: get recommended interval and skip decision
            yolo_interval = adaptive_scheduler.get_yolo_interval()
            should_skip = adaptive_scheduler.should_skip_yolo()

            now = time.perf_counter()
            if should_skip or (now - self._last_detect_time) < yolo_interval:
                continue
            self._last_detect_time = now

            frame = self._broker.get_frame()
            if frame is None:
                continue

            t0 = time.perf_counter()

            # Track frame age
            capture_ts = self._broker.get_capture_ts()
            if capture_ts > 0:
                frame_age_ms = (t0 - capture_ts) * 1000.0
                profiler.set_frame_age(frame_age_ms)

            h, w = frame.shape[:2]
            cam_matrix = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float32)
            dist_coeffs = np.zeros((4, 1), dtype=np.float32)

            results = self._model.predict(
                frame, verbose=False, imgsz=self.imgsz, conf=self.conf_threshold
            )

            detected = []
            if results and len(results[0].boxes) > 0:
                for box in results[0].boxes:
                    xyxy = box.xyxy[0].cpu().numpy()
                    cls_id = int(box.cls[0].cpu().item())
                    name = results[0].names[cls_id]
                    conf = float(box.conf[0].cpu().item())

                    x1, y1, x2, y2 = xyxy
                    image_pts = np.array(
                        [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32
                    )

                    success, rvec, tvec = cv2.solvePnP(
                        self.object_3d, image_pts, cam_matrix, dist_coeffs,
                        flags=cv2.SOLVEPNP_ITERATIVE
                    )

                    z_m = 0.0
                    if success:
                        z_m = abs(tvec[2][0]) / 1000.0

                    detected.append(DetectedObject(
                        name=name,
                        confidence=conf,
                        box=[int(x1), int(y1), int(x2), int(y2)],
                        distance_z=round(z_m, 3),
                    ))

            self._perception.update_objects(detected, frame_id=self._broker.get_frame_id())

            ms = (time.perf_counter() - t0) * 1000.0
            profiler._record_stage("yolo", ms)