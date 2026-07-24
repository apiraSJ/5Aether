"""
Object Spatial Plugin (Phase D) - YOLOv8 + solvePnP as a plugin.

Rewrites legacy perception/object_plugin.py as a PluginBase that emits
object detection events with 3D spatial distance.
"""

import threading
import time
import cv2
import numpy as np
from ultralytics import YOLO

from aether.core.plugin import PluginBase
from aether.core.event_bus import EventBus


class CameraPlugin(PluginBase):
    """Camera capture plugin - provides frames to FrameBroker."""
    
    name = "camera"
    
    def __init__(self, config=None):
        super().__init__()
        self.config = config or {}
        self._broker = None
        self._running = False
        self._thread = None
        self._cap = None
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self._broker = container.resolve("frame_broker")
        
        # Open camera
        device = self.config.get("device_index", 0)
        width = self.config.get("width", 640)
        height = self.config.get("height", 480)
        fps = self.config.get("fps", 30)
        
        self._cap = cv2.VideoCapture(device)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)
        
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
    
    def shutdown(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
    
    def _capture_loop(self):
        while self._running:
            ret, frame = self._cap.read()
            if ret:
                # Mirror for natural interaction
                frame = cv2.flip(frame, 1)
                self._broker.update_frame(frame)
            else:
                time.sleep(0.01)


class ObjectSpatialPlugin(PluginBase):
    """YOLOv8 object detection + solvePnP distance estimation."""
    
    name = "object_spatial"
    
    def __init__(self, model_path="yolov8n.pt", config=None):
        super().__init__()
        self.model_path = model_path
        self.config = config or {}
        self._broker = None
        self._running = False
        self._thread = None
        self._frame_event = None
        self._model = None
    
    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self._broker = container.resolve("frame_broker")
        
        self._frame_event = self._broker.register_consumer("object_spatial")
        
        # Load YOLO model
        self._model = YOLO(self.model_path)
        self.conf_threshold = self.config.get("confidence", 0.25)
        self.imgsz = self.config.get("imgsz", 320)
        
        # 3D object points for solvePnP (generic box)
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
            
            frame = self._broker.get_frame()
            if frame is None:
                continue
            
            h, w = frame.shape[:2]
            # Dynamic intrinsics
            cam_matrix = np.array([[w, 0, w/2], [0, w, h/2], [0, 0, 1]], dtype=np.float32)
            dist_coeffs = np.zeros((4, 1), dtype=np.float32)
            
            results = self._model.predict(frame, verbose=False, imgsz=self.imgsz, conf=self.conf_threshold)
            
            detected = []
            if results and len(results[0].boxes) > 0:
                for box in results[0].boxes:
                    xyxy = box.xyxy[0].cpu().numpy()
                    cls_id = int(box.cls[0].cpu().item())
                    name = results[0].names[cls_id]
                    conf = float(box.conf[0].cpu().item())
                    
                    x1, y1, x2, y2 = xyxy
                    image_pts = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
                    
                    success, rvec, tvec = cv2.solvePnP(
                        self.object_3d, image_pts, cam_matrix, dist_coeffs,
                        flags=cv2.SOLVEPNP_ITERATIVE
                    )
                    
                    z_m = 0.0
                    if success:
                        z_m = abs(tvec[2][0]) / 1000.0
                    
                    detected.append({
                        "name": name,
                        "conf": conf,
                        "box": [int(x1), int(y1), int(x2), int(y2)],
                        "distance_z": round(z_m, 3)
                    })
            
            if self.event_bus:
                self.event_bus.publish("vision_object_detected", {"objects": detected})
            
            time.sleep(0.04)  # ~25 FPS cap