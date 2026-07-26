"""
Camera Plugin and FrameBroker — vision pipeline entry point.

Architecture:
    CameraPlugin (thread) -> FrameBroker -> YOLOPlugin / MediaPipePlugin

FrameBroker acts as a central frame distribution system:
- CameraPlugin reads camera and updates latest_frame
- Plugins pull frames at their own FPS (not event-driven)
- FrameBroker emits vision.frame.ready with timestamp only (never frame data)
- No EventBus flooding — plugins pull frames when ready

Data flow:
    Camera -> FrameBroker -> vision.frame.ready -> Plugin pulls frame -> vision.object.detected
"""

from __future__ import annotations

import logging
import threading
import time

from aether.core.plugin import PluginBase
from aether.core.frame_broker import FrameBroker
from aether.core.profiler import profiler

logger = logging.getLogger("Aether.Camera")


class CameraPlugin(PluginBase):
    """Camera capture plugin.

    Single responsibility: read camera frames and feed FrameBroker.
    Does NOT do any vision processing.

    Architecture:
        CameraPlugin (thread) -> FrameBroker -> vision.frame.ready -> Plugins

    Why single thread:
    - Camera read is I/O bound (blocking)
    - Only one consumer of camera hardware
    - FrameBroker handles distribution to multiple plugins
    """

    name = "camera"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__()
        self.config = config or {}
        self._broker: FrameBroker | None = None
        self._event_bus = None
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._cap = None

    def initialize(self, container) -> None:
        """Initialize camera and register with FrameBroker."""
        self._event_bus = container.resolve("event_bus")
        self._broker = container.resolve("frame_broker")

        # Set EventBus on broker for frame.ready emission
        self._broker.set_event_bus(self._event_bus)

        # Open camera
        device = self.config.get("device_index", 0)
        width = self.config.get("width", 640)
        height = self.config.get("height", 480)
        fps = self.config.get("fps", 30)

        self._cap = self._open_camera(device, width, height, fps)

        if self._cap is None:
            logger.error("CameraPlugin: could not open camera device %d", device)
            return

        # Emit camera started event
        self._event_bus.publish_now(
            "vision.camera.started",
            {
                "device": device,
                "width": width,
                "height": height,
                "fps": fps,
            },
            source="camera",
        )

        logger.info("CameraPlugin: camera opened (device=%d, %dx%d @ %dfps)",
                     device, width, height, fps)

        # Start capture thread
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _open_camera(self, device: int, width: int, height: int, fps: int):
        """Open camera with backend preference for low latency."""
        try:
            import cv2
            import platform

            cap = None
            # Prefer DirectShow on Windows for lower latency
            if platform.system() == "Windows":
                try:
                    cap = cv2.VideoCapture(device, cv2.CAP_DSHOW)
                except Exception:
                    pass

            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(device)

            if cap is not None and cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                cap.set(cv2.CAP_PROP_FPS, fps)
                # Reduce buffer to 1 frame for lowest latency
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return cap

            logger.warning("CameraPlugin: could not open camera device %d", device)
            return None
        except ImportError:
            logger.warning("CameraPlugin: OpenCV (cv2) not available, using dummy camera")
            return None
        except Exception as e:
            logger.error("CameraPlugin: failed to open camera: %s", e)
            return None

    def shutdown(self) -> None:
        """Stop camera capture and release resources."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass

        # Emit camera stopped event
        if self._event_bus:
            self._event_bus.publish_now(
                "vision.camera.stopped",
                {},
                source="camera",
            )

        logger.info("CameraPlugin: shutdown complete")

    def _capture_loop(self) -> None:
        """Main capture loop. Reads frames and feeds FrameBroker."""
        if self._cap is None:
            # Dummy mode: emit frame.ready periodically for testing
            logger.info("CameraPlugin: running in dummy mode (no camera)")
            while self._running:
                self._broker.update_frame(None)
                time.sleep(1.0 / 30.0)
            return

        while self._running:
            t0 = time.perf_counter()
            ret, frame = self._cap.read()
            if ret:
                # Mirror for natural interaction (like a mirror)
                import cv2
                frame = cv2.flip(frame, 1)
                self._broker.update_frame(frame, capture_ts=t0)
                ms = (time.perf_counter() - t0) * 1000.0
                profiler._record_stage("camera", ms)
            else:
                # Camera read failed, wait briefly
                time.sleep(0.01)
