import unittest
import numpy as np

from vision.spatial import SpatialEstimator


class TestSpatialEstimator(unittest.TestCase):
    def test_estimate_returns_distance_for_valid_box(self):
        est = SpatialEstimator()
        # A 200x280 box roughly centered in a 640x480 frame
        dist = est.estimate((220, 100, 420, 380))
        self.assertIsNotNone(dist)
        self.assertGreater(dist, 0)

    def test_estimate_returns_none_for_none_box(self):
        est = SpatialEstimator()
        self.assertIsNone(est.estimate(None))

    def test_estimate_returns_none_for_degenerate_box(self):
        est = SpatialEstimator()
        self.assertIsNone(est.estimate((100, 100, 100, 200)))
        self.assertIsNone(est.estimate((200, 200, 100, 100)))

    def test_object_size_config_applied(self):
        est = SpatialEstimator({"object_width_cm": 10.0, "object_height_cm": 10.0})
        self.assertEqual(est.object_width_cm, 10.0)
        self.assertEqual(est.object_height_cm, 10.0)
        self.assertEqual(len(est.object_points), 4)


if __name__ == "__main__":
    unittest.main()
