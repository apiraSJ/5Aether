import time

class Telemetry:
    """Stores and updates real-time telemetry like FPS, latencies, and spatial info."""
    def __init__(self):
        self.last_frame_time = time.perf_counter()
        self.fps = 0.0
        self.inference_time = 0.0
        self.pnp_time = 0.0
        self.distance = 0.0
        self.pose_rvec = None
        self.pose_tvec = None

    def update_fps(self):
        """Updates rolling FPS estimation based on frame arrival delta."""
        now = time.perf_counter()
        delta = now - self.last_frame_time
        self.last_frame_time = now
        
        if delta > 0:
            current_fps = 1.0 / delta
            # Smooth out FPS transitions using exponential moving average
            if self.fps == 0.0:
                self.fps = current_fps
            else:
                self.fps = 0.9 * self.fps + 0.1 * current_fps

    def get_metrics_dict(self):
        """Returns a dict representation of telemetry for overlays or logging."""
        return {
            "fps": self.fps,
            "inference_time_ms": self.inference_time * 1000.0,
            "pnp_time_ms": self.pnp_time * 1000.0,
            "distance_cm": self.distance,
        }
