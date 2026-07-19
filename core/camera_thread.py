import cv2
import threading
import queue
import logging
import time


class CameraThread:
    def __init__(self, camera_config: dict, frame_queue: queue.Queue = None):
        self.logger = logging.getLogger("Aether.CameraThread")
        self.device_index = camera_config.get("device_index", 0)
        self.width = camera_config.get("width", 640)
        self.height = camera_config.get("height", 480)
        self.fps_target = camera_config.get("fps_target", 30)
        self.frame_queue = frame_queue or queue.Queue(maxsize=2)
        self.cap = None
        self.thread = None
        self.running = False
        self._lock = threading.Lock()

    def start(self):
        self.cap = cv2.VideoCapture(self.device_index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        if not self.cap.isOpened():
            self.logger.error(f"Failed to open camera {self.device_index}")
            raise RuntimeError(f"Cannot open camera {self.device_index}")

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        self.logger.info(f"Camera started (index={self.device_index})")

    def _capture_loop(self):
        frame_interval = 1.0 / self.fps_target
        while self.running:
            start = time.perf_counter()
            ret, frame = self.cap.read()

            if ret:
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                self.frame_queue.put(frame)
            else:
                self.logger.warning("Failed to capture frame")

            elapsed = time.perf_counter() - start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def get_frame(self):
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None

    def read(self):
        return self.get_frame()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.cap and self.cap.isOpened():
            self.cap.release()
        self.logger.info("Camera stopped")

    @property
    def is_running(self):
        return self.running and self.cap is not None and self.cap.isOpened()
