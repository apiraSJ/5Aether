"""
Cursor Manager — Virtual cursor with proper ratio mapping

Maps camera coordinates (4:3) to screen (16:9) preserving aspect ratio.
Uses "contain" mode — cursor stays within bounds, no stretching.
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
    """Manages virtual cursor with proper camera→screen ratio mapping."""

    def __init__(
        self,
        screen_width: int = 1920,
        screen_height: int = 1080,
        camera_width: int = 640,
        camera_height: int = 480,
        smoothing: float = 0.35,
        dead_zone: float = 0.5,
        mirror_x: bool = True,
    ):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.camera_width = camera_width
        self.camera_height = camera_height
        self.smoothing = smoothing
        self.dead_zone = dead_zone
        self.mirror_x = mirror_x
        self.logger = logging.getLogger("Aether.CursorManager")

        # Precompute ratio mapping
        self._compute_ratio()

        self._state = CursorState()
        self._prev_x = 0.0
        self._prev_y = 0.0
        self._prev_time = time.time()
        self._initialized = False
        self.logger = logging.getLogger("Aether.CursorManager")

    def _compute_ratio(self):
        """Compute contain-mode mapping from camera to screen.
        
        Camera (4:3) → Screen (16:9):
        - Fit camera frame inside screen preserving aspect ratio
        - Map normalized camera coords to screen coords within that region
        """
        cam_aspect = self.camera_width / self.camera_height   # 4/3 = 1.333
        scr_aspect = self.screen_width / self.screen_height   # 16/9 = 1.778

        if cam_aspect > scr_aspect:
            # Camera wider than screen — fit to width
            self._scale = self.screen_width / self.camera_width
        else:
            # Camera taller than screen — fit to height
            self._scale = self.screen_height / self.camera_height

        # Offset to center the mapped region
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
        # Mirror X if needed
        x = (1.0 - norm_x) if self.mirror_x else norm_x
        y = norm_y

        # Map through ratio
        screen_x = x * self.camera_width * self._scale + self._offset_x
        screen_y = y * self.camera_height * self._scale + self._offset_y

        return (screen_x, screen_y)

    def update(
        self,
        hand_x: float,
        hand_y: float,
        gesture: str = "Unknown",
        gesture_score: float = 0.0,
        is_pinch: bool = False,
        is_grab: bool = False,
    ):
        """Update cursor. Movement only during Pointing_Up."""
        now = time.time()
        dt = max(now - self._prev_time, 0.001)

        self._state.gesture = gesture
        self._state.gesture_score = gesture_score
        self._state.is_pinch = is_pinch
        self._state.is_grab = is_grab
        self._state.visible = True
        self._state.timestamp = now

        # Always compute screen position (for display)
        sx, sy = self.camera_to_screen(hand_x, hand_y)
        self._state.screen_x = sx
        self._state.screen_y = sy

        if gesture == "Pointing_Up":
            self._state.moving = True

            if not self._initialized:
                self._state.x = sx
                self._state.y = sy
                self._prev_x = sx
                self._prev_y = sy
                self._initialized = True
            else:
                dx = sx - self._state.x
                dy = sy - self._state.y
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > self.dead_zone:
                    self._state.x += (sx - self._state.x) * self.smoothing
                    self._state.y += (sy - self._state.y) * self.smoothing

            vx = (self._state.x - self._prev_x) / dt
            vy = (self._state.y - self._prev_y) / dt
            self._state.velocity_x = vx
            self._state.velocity_y = vy
            self._state.speed = math.sqrt(vx * vx + vy * vy)
            self._prev_x = self._state.x
            self._prev_y = self._state.y
        else:
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
