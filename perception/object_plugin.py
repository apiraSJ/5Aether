import threading
import time
import logging
import cv2
import numpy as np
from ultralytics import YOLO

from core.frame_broker import FrameBroker
from core.event_bus import EventBus, EventType


class ObjectSpatialPlugin(threading.Thread):
    """Processes frames from the FrameBroker via YOLO and derives real-world
    spatial distance (Z vectors) using solvePnP.

    Runs as a daemon thread. Emits OBJECT_DETECTED events on the EventBus with
    serialized object observations: [{"name","conf","box","distance_z"}].
    """

    def __init__(self, broker: FrameBroker, bus: EventBus, model_weight: str, config: dict = None):
        super().__init__(daemon=True)
        self.broker = broker
        self.bus = bus
        self.config = config or {}
        self.logger = logging.getLogger("Aether.ObjectSpatialPlugin")
        self._running = True
        self._frame_event = self.broker.register_consumer("object_spatial")

        # Load YOLO
        self.model = YOLO(model_weight)
        self.confidence_threshold = self.config.get("confidence", 0.45)
        self.inference_imgsz = self.config.get("imgsz", 320)

        # 3D physical object points (millimeters) — generic bounding volume
        self.object_3d_points = np.array([
            [-75.0, 25.0, 0.0],
            [75.0, 25.0, 0.0],
            [75.0, -25.0, 0.0],
            [-75.0, -25.0, 0.0],
        ], dtype=np.float32)

        # Camera intrinsics (will be dynamically updated per frame resolution)
        self.cam_matrix = np.array([[800, 0, 320], [0, 800, 240], [0, 0, 1]], dtype=np.float32)
        self.dist_coeffs = np.zeros((4, 1), dtype=np.float32)

    def run(self):
        self.logger.info("Object spatial plugin ready")

        while self._running:
            self._frame_event.wait(timeout=1.0)
            if not self._running:
                break
            self._frame_event.clear()
            frame = self.broker.get_frame()
            if frame is None:
                continue

            h, w = frame.shape[:2]
            # Dynamic intrinsics from actual resolution
            self.cam_matrix = np.array(
                [[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], dtype=np.float32
            )

            results = self.model.predict(
                frame, verbose=False, imgsz=self.inference_imgsz, conf=self.confidence_threshold
            )
            detected_objects = []

            if results and len(results[0].boxes) > 0:
                for box in results[0].boxes:
                    xyxy = box.xyxy[0].cpu().numpy()
                    cls_id = int(box.cls[0].cpu().item())
                    name = results[0].names[cls_id]
                    conf = float(box.conf[0].cpu().item())

                    x1, y1, x2, y2 = xyxy
                    image_points_2d = np.array(
                        [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32
                    )

                    success, rvec, tvec = cv2.solvePnP(
                        self.object_3d_points, image_points_2d,
                        self.cam_matrix, self.dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
                    )

                    z_distance_meters = 0.0
                    if success:
                        z_distance_meters = abs(tvec[2][0]) / 1000.0

                    detected_objects.append({
                        "name": name,
                        "conf": conf,
                        "box": [int(x1), int(y1), int(x2), int(y2)],
                        "distance_z": round(z_distance_meters, 3),
                    })

            self.bus.emit(EventType.OBJECT_DETECTED, data={"objects": detected_objects}, source="yolo_plugin")
            time.sleep(0.04)  # ~25 FPS cap for YOLO

    def stop(self):
        self._running = False
        self._frame_event.set()
        self.join(timeout=2.0)
        self.broker.unregister_consumer("object_spatial")
        self.logger.info("Object spatial plugin stopped")
