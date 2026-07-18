import cv2
import logging

class Camera:
    """Wrapper around OpenCV's VideoCapture for robust frame capture."""
    def __init__(self, config: dict):
        self.device_index = config.get('device_index', 0)
        self.width = config.get('width', 640)
        self.height = config.get('height', 480)
        self.cap = cv2.VideoCapture(self.device_index)
        
        # Configure properties
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        
        self.logger = logging.getLogger("Aether.Camera")
        if not self.cap.isOpened():
            err_msg = f"Failed to open video capture device with index {self.device_index}"
            self.logger.error(err_msg)
            raise RuntimeError(err_msg)
            
        self.logger.info(f"Camera opened (index={self.device_index}, resolution={self.width}x{self.height})")

    def read(self):
        """Captures and returns the next frame."""
        return self.cap.read()

    def release(self):
        """Releases the camera device."""
        if self.cap.isOpened():
            self.cap.release()
            self.logger.info("Camera device released.")
