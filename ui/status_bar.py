import logging


class StatusBar:
    def __init__(self):
        self.logger = logging.getLogger("Aether.StatusBar")
        self.fps = 0.0
        self.inference_ms = 0.0
        self.pnp_ms = 0.0
        self.camera_status = "Disconnected"
        self.yolo_status = "Not loaded"
        self.hand_status = "Not loaded"

    def update(self, fps=0.0, inference_ms=0.0, pnp_ms=0.0):
        self.fps = fps
        self.inference_ms = inference_ms
        self.pnp_ms = pnp_ms

    def set_camera_status(self, status: str):
        self.camera_status = status

    def set_yolo_status(self, status: str):
        self.yolo_status = status

    def set_hand_status(self, status: str):
        self.hand_status = status

    def get_status_text(self) -> str:
        return f"FPS: {self.fps:.1f} | INF: {self.inference_ms:.1f}ms | PNP: {self.pnp_ms:.1f}ms"
