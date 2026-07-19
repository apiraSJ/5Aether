import unittest
import numpy as np
from unittest.mock import MagicMock

from core.perception_worker import PerceptionWorker, PerceptionSnapshot
from vision.gesture_engine import GestureEngine
from vision.command_confirmation import CommandConfirmation


class TestPerceptionWorker(unittest.TestCase):
    def _make_worker(self):
        event_bus = MagicMock()
        plugin_manager = MagicMock()
        camera = MagicMock()
        camera.get_frame.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        gesture_engine = GestureEngine({})
        command_confirmation = CommandConfirmation({})
        worker = PerceptionWorker(
            event_bus, plugin_manager, gesture_engine,
            command_confirmation, camera, {"fps_target": 30}
        )
        return worker

    def test_get_latest_returns_snapshot_initially(self):
        worker = self._make_worker()
        snap = worker.get_latest()
        self.assertIsInstance(snap, PerceptionSnapshot)
        self.assertEqual(snap.detections, [])
        self.assertEqual(snap.fps, 0.0)

    def test_get_fps_zero_before_start(self):
        worker = self._make_worker()
        self.assertEqual(worker.get_fps(), 0.0)

    def test_stop_idempotent(self):
        worker = self._make_worker()
        # Should not raise even though thread never started
        worker.stop()

    def test_camera_attached_after_construction(self):
        worker = self._make_worker()
        new_cam = MagicMock()
        worker.camera = new_cam
        self.assertIs(worker.camera, new_cam)


if __name__ == "__main__":
    unittest.main()
