import unittest
import numpy as np
import os
import sys

# Add parent directory to path so imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import load_config
from core.performance import PerformanceTimer, PerformanceTracker
from core.telemetry import Telemetry
from vision.geometry import calculate_distance
from vision.pnp import estimate_pose

class TestAether(unittest.TestCase):
    def test_config_loader(self):
        # Testing non-existent config should load defaults
        cfg = load_config("nonexistent_config.yaml")
        self.assertIn("camera", cfg)
        self.assertIn("model", cfg)
        self.assertEqual(cfg["camera"]["device_index"], 0)

    def test_performance_timer(self):
        with PerformanceTimer("TestTimer") as timer:
            # Short sleep simulation
            import time
            time.sleep(0.01)
        self.assertGreater(timer.elapsed, 0.0)

    def test_performance_tracker(self):
        tracker = PerformanceTracker()
        tracker.update("inference", 0.03)
        tracker.update("inference", 0.05)
        self.assertAlmostEqual(tracker.get_average("inference"), 0.04)

    def test_telemetry(self):
        tel = Telemetry()
        tel.inference_time = 0.015
        tel.pnp_time = 0.005
        metrics = tel.get_metrics_dict()
        self.assertAlmostEqual(metrics["inference_time_ms"], 15.0)
        self.assertAlmostEqual(metrics["pnp_time_ms"], 5.0)

    def test_geometry_distance(self):
        tvec = np.array([[3.0], [4.0], [0.0]])
        dist = calculate_distance(tvec)
        # norm of (3,4,0) is 5.0
        self.assertAlmostEqual(dist, 5.0)

    def test_pnp_estimation(self):
        # Minimal matrices
        camera_matrix = np.array([[500, 0, 320], [0, 500, 240], [0, 0, 1]], dtype=np.float32)
        dist_coeffs = np.zeros(4, dtype=np.float32)
        # Test estimating pose from bounding box
        rvec, tvec = estimate_pose((100, 100, 300, 300), camera_matrix, dist_coeffs)
        self.assertIsNotNone(rvec)
        self.assertIsNotNone(tvec)

if __name__ == '__main__':
    unittest.main()
