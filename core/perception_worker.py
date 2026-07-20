import logging
import time
import threading
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from core.perception_pipeline import PerceptionPipeline
from vision.gesture_engine import GestureEngine
from vision.gesture_executor import GestureActionExecutor
from vision.command_confirmation import CommandConfirmation
from vision.spatial import SpatialEstimator
from core.event_bus import EventType


@dataclass
class PerceptionSnapshot:
    """Thread-safe snapshot of the latest perception output."""

    detections: list = field(default_factory=list)
    pnp: list = field(default_factory=list)  # [{label, distance_cm, box, confidence}]
    hand_results: Any = None
    gestures: list = field(default_factory=list)  # active gesture labels
    actions: list = field(default_factory=list)  # actions executed this frame
    cursor: tuple = (0.5, 0.5)  # normalized cursor position
    is_dragging: bool = False
    mode: str = "passive"
    fps: float = 0.0
    timestamp: float = 0.0


class PerceptionWorker:
    """Runs YOLO + MediaPipe on a background thread at a throttled rate.

    Decouples heavy ML inference from the DearPyGui render loop so the UI
    stays at native frame rate while perception runs at a steady target FPS.
    """

    def __init__(
        self,
        event_bus,
        plugin_manager,
        gesture_engine: GestureEngine,
        command_confirmation: CommandConfirmation,
        camera,
        config: dict = None,
    ):
        self.logger = logging.getLogger("Aether.PerceptionWorker")
        self.event_bus = event_bus
        self.plugin_manager = plugin_manager
        self.gesture_engine = gesture_engine
        self.command_confirmation = command_confirmation
        self.camera = camera
        self.config = config or {}

        self.fps_target = self.config.get("fps_target", 15)
        self.spatial_estimator = SpatialEstimator(self.config.get("spatial", {}))

        # Gesture executor: maps gesture events → actions → bus events
        self.gesture_executor = GestureActionExecutor(event_bus, gesture_engine)

        self._pipeline = PerceptionPipeline(event_bus, plugin_manager)
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()
        self._snapshot = PerceptionSnapshot()
        self._frame_count = 0
        self._last_fps_time = time.time()
        self._fps = 0.0

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.logger.info(f"Perception worker started (target={self.fps_target} FPS)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.logger.info("Perception worker stopped")

    def get_latest(self) -> PerceptionSnapshot:
        with self._lock:
            return self._snapshot

    def get_fps(self) -> float:
        return self._fps

    def _loop(self):
        interval = 1.0 / self.fps_target
        while self._running:
            start = time.perf_counter()

            frame = self.camera.get_frame() if self.camera else None
            if frame is None:
                # No new camera frame; throttle lightly and continue
                time.sleep(0.01)
                continue

            self._process_frame(frame)

            # FPS accounting
            self._frame_count += 1
            now = time.time()
            elapsed = now - self._last_fps_time
            if elapsed >= 1.0:
                self._fps = self._frame_count / elapsed
                self._frame_count = 0
                self._last_fps_time = now

            # Sleep to maintain target rate
            took = time.perf_counter() - start
            sleep_time = interval - took
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _process_frame(self, frame):
        result = self._pipeline.process(frame)

        # PnP distance per detection
        pnp_list = []
        for det in result.detections:
            dist = self.spatial_estimator.estimate(det.get("box"))
            pnp_list.append(
                {
                    "label": det.get("label", "?"),
                    "confidence": det.get("confidence", 0.0),
                    "box": det.get("box"),
                    "distance_cm": dist,
                }
            )

        # Gestures + Actions
        gesture_labels = []
        action_labels = []
        cursor = (0.5, 0.5)
        is_dragging = False

        if result.hand_results and self.gesture_engine:
            # Run gesture recognition
            gesture_events = self.gesture_engine.update(result.hand_results)

            # Execute gesture → action mapping
            if self.gesture_executor:
                actions = self.gesture_executor.process_events(gesture_events)
                for a in actions:
                    gesture_labels.append(a.gesture.value)
                    action_labels.append(a.action.value)

                cursor = self.gesture_executor.get_cursor()
                is_dragging = False

            # Emit raw gesture events for legacy consumers
            for ge in gesture_events:
                if ge.gesture.value not in gesture_labels:
                    gesture_labels.append(ge.gesture.value)

                # Legacy command_confirmation still runs
                if self.command_confirmation:
                    actions = self.command_confirmation.handle_gesture(ge)
                    for action in actions:
                        if action.type == "CANCEL":
                            self.command_confirmation.cancel()

        mode = "passive"
        if self.command_confirmation and self.command_confirmation.has_pending:
            mode = "pointing"
        elif is_dragging:
            mode = "dragging"
        elif gesture_labels:
            mode = "active"

        # Batched object event (avoid per-detection bus spam)
        if result.detections:
            self.event_bus.emit(
                EventType.OBJECT_DETECTED,
                data={"count": len(result.detections), "objects": result.detections},
                source="perception_worker",
            )

        snapshot = PerceptionSnapshot(
            detections=result.detections,
            pnp=pnp_list,
            hand_results=result.hand_results,
            gestures=gesture_labels,
            actions=action_labels,
            cursor=cursor,
            is_dragging=is_dragging,
            mode=mode,
            fps=self._fps,
            timestamp=time.time(),
        )

        with self._lock:
            self._snapshot = snapshot
