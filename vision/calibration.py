import numpy as np
import logging
import os
import yaml

class Calibration:
    """Loads camera intrinsic matrix and distortion coefficients."""
    def __init__(self, width=640, height=480, calibration_file=None):
        self.logger = logging.getLogger("Aether.Calibration")
        self.width = width
        self.height = height
        
        # Load or generate default intrinsics
        if calibration_file and os.path.exists(calibration_file):
            self.load_calibration(calibration_file)
        else:
            self.logger.warning("No calibration file specified or found. Using generic pinhole approximation.")
            self.generate_defaults()

    def generate_defaults(self):
        """Generates default intrinsic matrix based on standard webcam FOV assumptions."""
        # Simple pinhole approximation: focal length roughly equal to width
        focal_length = self.width
        center_x = self.width / 2.0
        center_y = self.height / 2.0
        
        self.camera_matrix = np.array([
            [focal_length, 0.0, center_x],
            [0.0, focal_length, center_y],
            [0.0, 0.0, 1.0]
        ], dtype=np.float32)
        
        self.dist_coeffs = np.zeros(4, dtype=np.float32)

    def load_calibration(self, filepath):
        """Loads camera matrices from a YAML file."""
        try:
            with open(filepath, 'r') as f:
                data = yaml.safe_load(f)
            
            self.camera_matrix = np.array(data['camera_matrix'], dtype=np.float32)
            self.dist_coeffs = np.array(data['dist_coeffs'], dtype=np.float32)
            self.logger.info(f"Successfully loaded camera calibration from {filepath}")
        except Exception as e:
            self.logger.error(f"Failed to load calibration file {filepath}: {e}. Falling back to default calibration.")
            self.generate_defaults()
