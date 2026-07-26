"""AdaptiveScheduler — central scheduling logic for vision pipeline and render.

Replaces fixed update rates with dynamic scheduling based on:
  - Tick budget usage (main thread)
  - Frame age (how stale is the data)
  - End-to-end latency
  - Worker thread load

Provides recommended intervals for:
  - YOLO (object detection)
  - MediaPipe (hand/gesture)
  - VisionAdapter (state building + event emission)
  - Render layers (HUD)

All vision plugins and HUDManager should query this scheduler instead of
using hardcoded intervals.
"""

from __future__ import annotations

import logging
import time
import threading
from dataclasses import dataclass
from typing import Callable

from aether.core.profiler import profiler

logger = logging.getLogger("Aether.Scheduler")


@dataclass
class SchedulerConfig:
    """Configuration for adaptive scheduler.

    Hardware Reference: USB Webcam 30fps, CPU-only YOLOv8n, MediaPipe Hands.
    Budgets adjusted to match hardware reality (not idealized targets).
    """
    # Tick budget (main thread) - target 33ms for 30 FPS
    tick_budget_ms: float = 33.0
    # Target frame age - if exceeded, begin pressure-based throttling
    target_frame_age_ms: float = 45.0
    # Max frame age before aggressive frame skip (raised from 60→85:
    # at 30fps camera, frame_age is inherently ~65ms; 60ms skipped YOLO
    # almost entirely. 85ms allows YOLO to run at ~5-8Hz.)
    max_frame_age_ms: float = 85.0
    # Min frame age to resume normal rate
    min_frame_age_ms: float = 30.0
    # End-to-end latency targets (120ms for hardware reference)
    target_e2e_ms: float = 100.0
    max_e2e_ms: float = 200.0
    # Minimum intervals (lower bounds)
    min_yolo_interval: float = 1.0 / 10.0   # 10 Hz max
    min_mediapipe_interval: float = 1.0 / 15.0  # 15 Hz max
    min_vision_interval: float = 1.0 / 8.0    # 8 Hz max
    # Maximum intervals (upper bounds)
    max_yolo_interval: float = 1.0 / 3.0    # 3 Hz min
    max_mediapipe_interval: float = 1.0 / 5.0  # 5 Hz min
    max_vision_interval: float = 1.0 / 3.0   # 3 Hz min


@dataclass
class SchedulerState:
    """Current scheduler outputs."""
    yolo_interval: float
    mediapipe_interval: float
    vision_interval: float
    layer_intervals: dict[int, float]  # layer -> interval
    skip_yolo: bool
    skip_mediapipe: bool
    skip_vision: bool
    cpu_load_pct: float
    frame_age_ms: float
    e2e_latency_ms: float
    tick_used_ms: float
    tick_overrun_ms: float


class AdaptiveScheduler:
    """Central adaptive scheduler for vision pipeline and render.

    Uses profiler metrics to dynamically adjust:
    - Vision processing rates (YOLO, MediaPipe, VisionAdapter)
    - Render layer update intervals
    - Frame skip decisions

    Thread-safe: can be called from main thread and worker threads.
    """

    def __init__(self, config: SchedulerConfig | None = None, debug: bool = False) -> None:
        self._config = config or SchedulerConfig()
        self._debug = debug
        self._lock = threading.RLock()
        self._last_update: float = 0.0
        self._update_interval = 0.5  # Update scheduler decisions every 500ms

        # Current state
        self._state = SchedulerState(
            yolo_interval=self._config.min_yolo_interval,
            mediapipe_interval=self._config.min_mediapipe_interval,
            vision_interval=self._config.min_vision_interval,
            layer_intervals={
                0: 0.0,      # camera - every frame
                1: 0.0,      # overlay - every frame
                2: 0.1,      # status/gesture/objects - 10 Hz
                3: 0.2,      # timeline/perf_hud - 5 Hz
            },
            skip_yolo=False,
            skip_mediapipe=False,
            skip_vision=False,
            cpu_load_pct=0.0,
            frame_age_ms=0.0,
            e2e_latency_ms=0.0,
            tick_used_ms=0.0,
            tick_overrun_ms=0.0,
        )

        # History for smoothing
        self._yolo_interval_hist: list[float] = []
        self._mediapipe_interval_hist: list[float] = []
        self._vision_interval_hist: list[float] = []
        self._max_hist_len = 5

        # Callbacks for external notification
        self._on_state_change: list[Callable[[SchedulerState], None]] = []

    def register_callback(self, callback: Callable[[SchedulerState], None]) -> None:
        """Register callback to be notified when scheduler state changes."""
        with self._lock:
            self._on_state_change.append(callback)

    def update(self) -> SchedulerState:
        """Update scheduler decisions based on current profiler metrics.

        Should be called periodically (e.g., every 500ms) from main thread.
        """
        now = time.perf_counter()
        if now - self._last_update < self._update_interval:
            return self._state

        self._last_update = now

        # Get current profiler snapshot
        snap = profiler.snapshot()

        # Extract metrics
        tick_used = snap.tick_used_ms
        tick_budget = snap.tick_budget_ms
        tick_overrun = snap.tick_overrun_ms
        frame_age = snap.frame_age_ms
        e2e_latency = snap.e2e_latency_ms

        # Compute CPU load percentage from tick usage
        cpu_load = min(100.0, (tick_used / tick_budget) * 100.0) if tick_budget > 0 else 0.0

        # Decision logic
        new_state = self._compute_state(
            cpu_load, frame_age, e2e_latency, tick_used, tick_overrun
        )

        if self._debug:
            logger.info(
                "Scheduler update: frame_age=%.1f e2e=%.1f tick_used=%.1f/%.1f "
                "overrun=%.1f cpu=%.0f%% skip=[yolo=%s mp=%s vis=%s] "
                "intervals=[yolo=%.3f mp=%.3f vis=%.3f]",
                frame_age, e2e_latency, tick_used, tick_budget, tick_overrun,
                cpu_load, new_state.skip_yolo, new_state.skip_mediapipe,
                new_state.skip_vision, new_state.yolo_interval,
                new_state.mediapipe_interval, new_state.vision_interval,
            )

        with self._lock:
            self._state = new_state
            # Notify callbacks
            for cb in self._on_state_change:
                try:
                    cb(new_state)
                except Exception:
                    pass  # Don't let callback errors break scheduler

        return self._state

    def _compute_state(
        self,
        cpu_load: float,
        frame_age: float,
        e2e_latency: float,
        tick_used: float,
        tick_overrun: float,
    ) -> SchedulerState:
        """Compute new scheduler state from metrics."""
        cfg = self._config

        # --- Determine pressure level ---
        # Pressure combines tick overrun, frame age, and E2E latency
        pressure = 0.0

        if tick_overrun > 0:
            pressure += min(1.0, tick_overrun / 10.0) * 0.4  # 40% weight
        if frame_age > cfg.target_frame_age_ms:
            pressure += min(1.0, (frame_age - cfg.target_frame_age_ms) / cfg.max_frame_age_ms) * 0.35  # 35%
        if e2e_latency > cfg.target_e2e_ms:
            pressure += min(1.0, (e2e_latency - cfg.target_e2e_ms) / cfg.max_e2e_ms) * 0.25  # 25%

        pressure = min(1.0, pressure)

        # --- Compute intervals based on pressure ---
        # Low pressure = fast rates, High pressure = slow rates

        # YOLO interval
        yolo_range = cfg.max_yolo_interval - cfg.min_yolo_interval
        yolo_interval = cfg.min_yolo_interval + pressure * yolo_range

        # MediaPipe interval
        mp_range = cfg.max_mediapipe_interval - cfg.min_mediapipe_interval
        mp_interval = cfg.min_mediapipe_interval + pressure * mp_range

        # Vision interval
        vis_range = cfg.max_vision_interval - cfg.min_vision_interval
        vis_interval = cfg.min_vision_interval + pressure * vis_range

        # Smooth intervals (exponential moving average)
        yolo_interval = self._smooth("yolo", yolo_interval)
        mp_interval = self._smooth("mediapipe", mp_interval)
        vis_interval = self._smooth("vision", vis_interval)

        # --- Frame skip decisions ---
        # Skip YOLO if frame is too old (stale data) or severe overrun
        skip_yolo = frame_age > cfg.max_frame_age_ms or tick_overrun > 10.0

        # Skip MediaPipe if frame is very old
        skip_mediapipe = frame_age > cfg.max_frame_age_ms * 1.5

        # Skip Vision if frame is stale
        skip_vision = frame_age > cfg.max_frame_age_ms * 1.2

        # --- Layer intervals ---
        # Under high pressure, slow down non-critical layers
        layer_intervals = {
            0: 0.0,   # Camera - always full rate
            1: 0.0 if pressure < 0.7 else 1.0 / 30.0,  # Overlay - full or 30Hz
            2: 0.1 if pressure < 0.5 else (0.2 if pressure < 0.8 else 0.5),  # 10/5/2 Hz
            3: 0.2 if pressure < 0.5 else (0.5 if pressure < 0.8 else 1.0),  # 5/2/1 Hz
        }

        return SchedulerState(
            yolo_interval=yolo_interval,
            mediapipe_interval=mp_interval,
            vision_interval=vis_interval,
            layer_intervals=layer_intervals,
            skip_yolo=skip_yolo,
            skip_mediapipe=skip_mediapipe,
            skip_vision=skip_vision,
            cpu_load_pct=cpu_load,
            frame_age_ms=frame_age,
            e2e_latency_ms=e2e_latency,
            tick_used_ms=tick_used,
            tick_overrun_ms=tick_overrun,
        )

    def _smooth(self, key: str, value: float) -> float:
        """Apply exponential moving average smoothing."""
        hist_attr = f"_{key}_interval_hist"
        hist = getattr(self, hist_attr)
        hist.append(value)
        if len(hist) > self._max_hist_len:
            hist.pop(0)
        # EMA with alpha=0.3 (favor recent but stable)
        ema = hist[0]
        for v in hist[1:]:
            ema = 0.3 * v + 0.7 * ema
        return ema

    def get_state(self) -> SchedulerState:
        """Get current scheduler state (thread-safe)."""
        with self._lock:
            return self._state

    def get_yolo_interval(self) -> float:
        """Get recommended YOLO processing interval (seconds)."""
        with self._lock:
            return self._state.yolo_interval

    def get_mediapipe_interval(self) -> float:
        """Get recommended MediaPipe processing interval (seconds)."""
        with self._lock:
            return self._state.mediapipe_interval

    def get_vision_interval(self) -> float:
        """Get recommended VisionAdapter processing interval (seconds)."""
        with self._lock:
            return self._state.vision_interval

    def should_skip_yolo(self) -> bool:
        """Check if YOLO should skip this cycle."""
        with self._lock:
            return self._state.skip_yolo

    def should_skip_mediapipe(self) -> bool:
        """Check if MediaPipe should skip this cycle."""
        with self._lock:
            return self._state.skip_mediapipe

    def should_skip_vision(self) -> bool:
        """Check if VisionAdapter should skip this cycle."""
        with self._lock:
            return self._state.skip_vision

    def get_layer_intervals(self) -> dict[int, float]:
        """Get render layer intervals."""
        with self._lock:
            return self._state.layer_intervals.copy()

    def get_metrics(self) -> dict:
        """Get current metrics for HUD display."""
        with self._lock:
            s = self._state
            return {
                "yolo_hz": 1.0 / s.yolo_interval if s.yolo_interval > 0 else 0,
                "mediapipe_hz": 1.0 / s.mediapipe_interval if s.mediapipe_interval > 0 else 0,
                "vision_hz": 1.0 / s.vision_interval if s.vision_interval > 0 else 0,
                "cpu_load": s.cpu_load_pct,
                "frame_age": s.frame_age_ms,
                "e2e_latency": s.e2e_latency_ms,
                "tick_used": s.tick_used_ms,
                "tick_overrun": s.tick_overrun_ms,
                "skip_yolo": s.skip_yolo,
                "skip_mediapipe": s.skip_mediapipe,
                "skip_vision": s.skip_vision,
                "layer_2_hz": 1.0 / s.layer_intervals.get(2, 0.1) if s.layer_intervals.get(2, 0) > 0 else 0,
                "layer_3_hz": 1.0 / s.layer_intervals.get(3, 0.2) if s.layer_intervals.get(3, 0) > 0 else 0,
            }


# Global instance
adaptive_scheduler = AdaptiveScheduler()