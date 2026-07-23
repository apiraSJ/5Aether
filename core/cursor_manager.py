"""
Cursor Manager — Virtual cursor with adaptive smoothing & velocity prediction

Maps camera coordinates (4:3) to screen (16:9) preserving aspect ratio.
Uses "contain" mode — cursor stays within bounds, no stretching.

Key improvements over v1:
- Adaptive smoothing: fast movement = responsive, slow movement = stable
- Velocity prediction: reduces perceived lag
- Proper dead zone: larger when moving fast, smaller when slow
- Screen edge clamping: cursor stays on-screen
- Sensitivity multiplier: like mouse DPI
"""

import time
import math
import logging
from typing import Tuple
from dataclasses import dataclass


@dataclass
class CursorState:
    x: float = 0.0
    y: float = 0.0
    screen_x: float = 0.0
    screen_y: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    speed: float = 0.0
    gesture: str = "Unknown"
    gesture_score: float = 0.0
    is_pinch: bool = False
    is_grab: bool = False
    visible: bool = False
    moving: bool = False
    timestamp: float = 0.0


class CursorManager:
    """Manages virtual cursor with adaptive smoothing and velocity prediction."""

    def __init__(
        self,
        screen_width: int = 1920,
        screen_height: int = 1080,
        camera_width: int = 640,
        camera_height: int = 480,
        smoothing: float = 0.25,
        dead_zone: float = 2.0,
        mirror_x: bool = True,
        sensitivity: float = 1.0,
        prediction: float = 0.08,
    ):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.camera_width = camera_width
        self.camera_height = camera_height
        self.base_smoothing = smoothing
        self.base_dead_zone = dead_zone
        self.mirror_x = mirror_x
        self.sensitivity = sensitivity
        self.prediction = prediction
        self.logger = logging.getLogger("Aether.CursorManager")

        # Precompute ratio mapping
        self._compute_ratio()

        self._state = CursorState()
        self._smooth_x = 0.0
        self._smooth_y = 0.0
        self._prev_x = 0.0
        self._prev_y = 0.0
        self._prev_time = time.time()
        self._initialized = False

    def _compute_ratio(self):
        """Compute contain-mode mapping from camera to screen.

        Camera (4:3) → Screen (16:9):
        - Fit camera frame inside screen preserving aspect ratio
        - Map normalized camera coords to screen coords within that region
        """
        cam_aspect = self.camera_width / self.camera_height
        scr_aspect = self.screen_width / self.screen_height

        if cam_aspect > scr_aspect:
            self._scale = self.screen_width / self.camera_width
        else:
            self._scale = self.screen_height / self.camera_height

        mapped_w = self.camera_width * self._scale
        mapped_h = self.camera_height * self._scale
        self._offset_x = (self.screen_width - mapped_w) / 2.0
        self._offset_y = (self.screen_height - mapped_h) / 2.0

        self.logger.info(
            f"Ratio map: cam={self.camera_width}x{self.camera_height} "
            f"screen={self.screen_width}x{self.screen_height} "
            f"scale={self._scale:.3f} offset=({self._offset_x:.0f},{self._offset_y:.0f})"
        )

    def camera_to_screen(self, norm_x: float, norm_y: float) -> Tuple[float, float]:
        """Map normalized camera coords [0,1] to screen pixels."""
        x = (1.0 - norm_x) if self.mirror_x else norm_x
        y = norm_y

        screen_x = x * self.camera_width * self._scale + self._offset_x
        screen_y = y * self.camera_height * self._scale + self._offset_y

        return (screen_x, screen_y)

    def _clamp_to_screen(self, x: float, y: float) -> Tuple[float, float]:
        """Clamp cursor position to screen bounds."""
        x = max(0.0, min(float(self.screen_width - 1), x))
        y = max(0.0, min(float(self.screen_height - 1), y))
        return (x, y)

    def update(
        self,
        hand_x: float,
        hand_y: float,
        gesture: str = "Unknown",
        gesture_score: float = 0.0,
        is_pinch: bool = False,
        is_grab: bool = False,
    ):
        """Update cursor with adaptive smoothing and velocity prediction.

        Cursor tracks during any visible gesture except pinch (for click accuracy).
        """
        now = time.time()
        dt = max(now - self._prev_time, 0.001)

        self._state.gesture = gesture
        self._state.gesture_score = gesture_score
        self._state.is_pinch = is_pinch
        self._state.is_grab = is_grab
        self._state.visible = True
        self._state.timestamp = now

        # Raw screen position from camera
        raw_x, raw_y = self.camera_to_screen(hand_x, hand_y)
        self._state.screen_x = raw_x
        self._state.screen_y = raw_y

        # Track during any gesture except pinch (for click precision)
        should_track = not is_pinch and gesture != "Unknown"

        if should_track:
            self._state.moving = True

            if not self._initialized:
                self._smooth_x = raw_x
                self._smooth_y = raw_y
                self._prev_x = raw_x
                self._prev_y = raw_y
                self._initialized = True
            else:
                # Distance from current smoothed position to raw target
                dx = raw_x - self._smooth_x
                dy = raw_y - self._smooth_y
                dist = math.sqrt(dx * dx + dy * dy)

                # Adaptive smoothing: fast movement = more responsive
                speed = self._state.speed
                speed_factor = 1.0 + min(speed / 800.0, 1.5)
                alpha = min(self.base_smoothing * speed_factor, 0.85)

                # Adaptive dead zone: larger when moving fast
                dead = self.base_dead_zone * (1.0 + min(speed / 400.0, 2.0))

                if dist > dead:
                    self._smooth_x += dx * alpha
                    self._smooth_y += dy * alpha

                # Velocity prediction: nudge cursor in direction of movement
                pred_x = self._smooth_x + self._state.velocity_x * self.prediction * dt
                pred_y = self._smooth_y + self._state.velocity_y * self.prediction * dt
                pred_x, pred_y = self._clamp_to_screen(pred_x, pred_y)

                # Blend prediction (light touch, don't overshoot)
                self._smooth_x = self._smooth_x * 0.9 + pred_x * 0.1
                self._smooth_y = self._smooth_y * 0.9 + pred_y * 0.1

            # Clamp final position
            self._smooth_x, self._smooth_y = self._clamp_to_screen(
                self._smooth_x, self._smooth_y
            )

            self._state.x = self._smooth_x
            self._state.y = self._smooth_y

            # Compute velocity
            vx = (self._state.x - self._prev_x) / dt
            vy = (self._state.y - self._prev_y) / dt
            self._state.velocity_x = vx
            self._state.velocity_y = vy
            self._state.speed = math.sqrt(vx * vx + vy * vy)
            self._prev_x = self._state.x
            self._prev_y = self._state.y
        else:
            # During pinch: snap position to raw for hover detection
            # (cursor overlay freezes visually via moving=False flag)
            self._state.x = raw_x
            self._state.y = raw_y
            self._state.moving = False
            self._state.velocity_x = 0.0
            self._state.velocity_y = 0.0
            self._state.speed = 0.0

        self._prev_time = now

    def hide(self):
        self._state.visible = False
        self._state.moving = False
        self._initialized = False

    def get_state(self) -> CursorState:
        s = self._state
        return CursorState(
            x=s.x, y=s.y, screen_x=s.screen_x, screen_y=s.screen_y,
            velocity_x=s.velocity_x, velocity_y=s.velocity_y,
            speed=s.speed,
            gesture=s.gesture, gesture_score=s.gesture_score,
            is_pinch=s.is_pinch, is_grab=s.is_grab,
            visible=s.visible, moving=s.moving,
            timestamp=s.timestamp,
        )

    @property
    def position(self) -> Tuple[float, float]:
        return (self._state.x, self._state.y)

    @property
    def screen_position(self) -> Tuple[float, float]:
        return (self._state.screen_x, self._state.screen_y)

    @property
    def visible(self) -> bool:
        return self._state.visible

    @property
    def moving(self) -> bool:
        return self._state.moving

    @property
    def gesture(self) -> str:
        return self._state.gesture
