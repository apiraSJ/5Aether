import logging
import numpy as np
import cv2


class SpatialEstimator:
    """Estimates the distance (and pose) of a detected object using Perspective-n-Point.

    Ported from spatial_core.py. Uses approximate camera intrinsics; results are
    estimates suitable for a HUD, not metrology-grade measurements.
    """

    def __init__(self, config: dict = None):
        self.logger = logging.getLogger("Aether.SpatialEstimator")
        config = config or {}

        # Object physical size in centimeters (default: A4-like panel 21 x 29.7 cm)
        self.object_width_cm = config.get("object_width_cm", 21.0)
        self.object_height_cm = config.get("object_height_cm", 29.7)

        # Approximate camera intrinsics (standard 640x480 webcam)
        focal = config.get("focal_length", 640)
        cx = config.get("center_x", 320)
        cy = config.get("center_y", 240)
        self.camera_matrix = np.array(
            [[focal, 0, cx], [0, focal, cy], [0, 0, 1]], dtype=np.float32
        )
        self.dist_coeffs = np.zeros(4, dtype=np.float32)

        # 3D real-world coordinates of the object corners (cm), centered assumption:
        # Top-Left, Top-Right, Bottom-Right, Bottom-Left
        self.object_points = np.array(
            [
                [0.0, 0.0, 0.0],
                [self.object_width_cm, 0.0, 0.0],
                [self.object_width_cm, self.object_height_cm, 0.0],
                [0.0, self.object_height_cm, 0.0],
            ],
            dtype=np.float32,
        )

    def estimate(self, box) -> float | None:
        """Estimate distance (Z, in cm) from the camera to the object in `box`.

        box: (x1, y1, x2, y2) in pixels.
        Returns distance in cm, or None if PnP fails.
        """
        if box is None:
            return None

        x1, y1, x2, y2 = map(float, box)
        if x2 <= x1 or y2 <= y1:
            return None

        image_points = np.array(
            [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32
        )

        success, rvec, tvec = cv2.solvePnP(
            self.object_points,
            image_points,
            self.camera_matrix,
            self.dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success or tvec is None:
            return None

        return float(tvec[2][0])
