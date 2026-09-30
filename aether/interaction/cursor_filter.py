"""CursorFilter — smooths raw MediaPipe landmarks into stable cursor positions.

Features:
    1. One Euro Filter (adaptive low-pass)
    2. Dead zone (ignore small movements)
    3. Sensitivity control (amplify or dampen)
    4. Mirror X support (camera mirror → screen coordinates)

Pipeline:
    MediaPipe landmark → CursorFilter → CursorMapper → CursorController → EventBus
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class FilterConfig:
    """Configuration for CursorFilter."""

    min_cutoff: float = 1.0       # One Euro: minimum cutoff frequency
    beta: float = 0.5             # One Euro: speed coefficient
    dcutoff: float = 1.0          # One Euro: derivative cutoff
    dead_zone: float = 2.0        # Pixels: ignore movements smaller than this
    sensitivity: float = 1.0      # Multiplier: >1 = faster, <1 = slower
    mirror_x: bool = True         # Mirror horizontal axis
    screen_width: int = 1920      # Target screen width
    screen_height: int = 1080     # Target screen height
    camera_width: int = 640       # Source camera width
    camera_height: int = 480      # Source camera height


class _OneEuroFilter:
    """One Euro Filter for smooth cursor tracking.

    Reference: https://hal.inria.fr/hal-00670496/document
    """

    def __init__(self, min_cutoff: float = 1.0, beta: float = 0.5, dcutoff: float = 1.0) -> None:
        self._min_cutoff = min_cutoff
        self._beta = beta
        self._dcutoff = dcutoff
        self._x_prev: Optional[float] = None
        self._dx_prev: Optional[float] = None
        self._t_prev: Optional[float] = None

    def _alpha(self, cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt) if dt > 0 else 1.0

    def filter(self, x: float, t: Optional[float] = None) -> float:
        if t is None:
            t = time.perf_counter()

        if self._t_prev is None:
            self._x_prev = x
            self._dx_prev = 0.0
            self._t_prev = t
            return x

        dt = t - self._t_prev
        if dt <= 0:
            return self._x_prev or x

        dx = (x - self._x_prev) / dt
        alpha_d = self._alpha(self._dcutoff, dt)
        dx_hat = alpha_d * dx + (1 - alpha_d) * self._dx_prev

        cutoff = self._min_cutoff + self._beta * abs(dx_hat)
        alpha = self._alpha(cutoff, dt)
        x_hat = alpha * x + (1 - alpha) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t

        return x_hat

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = None
        self._t_prev = None


class CursorFilter:
    """Smooths raw cursor input with One Euro filtering, dead zone, and sensitivity.

    Usage:
        filt = CursorFilter(config)
        screen_x, screen_y = filt.process(raw_x, raw_y)
    """

    def __init__(self, config: Optional[FilterConfig] = None) -> None:
        self._config = config or FilterConfig()
        self._filter_x = _OneEuroFilter(
            min_cutoff=self._config.min_cutoff,
            beta=self._config.beta,
            dcutoff=self._config.dcutoff,
        )
        self._filter_y = _OneEuroFilter(
            min_cutoff=self._config.min_cutoff,
            beta=self._config.beta,
            dcutoff=self._config.dcutoff,
        )
        self._last_x: Optional[float] = None
        self._last_y: Optional[float] = None

    def process(self, raw_x: float, raw_y: float) -> tuple[float, float]:
        """Process raw input coordinates and return filtered screen coordinates.

        Args:
            raw_x: Raw x coordinate (0.0–1.0 from MediaPipe, or pixel coords)
            raw_y: Raw y coordinate (0.0–1.0 from MediaPipe, or pixel coords)

        Returns:
            (screen_x, screen_y) in screen pixel coordinates.
        """
        cfg = self._config

        # Normalize to [0,1] if needed
        nx = raw_x / cfg.camera_width if raw_x > 1.0 else raw_x
        ny = raw_y / cfg.camera_height if raw_y > 1.0 else raw_y

        # Mirror X
        if cfg.mirror_x:
            nx = 1.0 - nx

        # Apply sensitivity
        nx = 0.5 + (nx - 0.5) * cfg.sensitivity
        ny = 0.5 + (ny - 0.5) * cfg.sensitivity

        # Clamp
        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))

        # One Euro filter
        fx = self._filter_x.filter(nx)
        fy = self._filter_y.filter(ny)

        # Convert to screen pixels
        sx = fx * cfg.screen_width
        sy = fy * cfg.screen_height

        # Dead zone
        if self._last_x is not None and self._last_y is not None:
            dx = sx - self._last_x
            dy = sy - self._last_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < cfg.dead_zone:
                return self._last_x, self._last_y

        self._last_x = sx
        self._last_y = sy
        return sx, sy

    def reset(self) -> None:
        """Reset filter state."""
        self._filter_x.reset()
        self._filter_y.reset()
        self._last_x = None
        self._last_y = None

    @property
    def config(self) -> FilterConfig:
        return self._config

    def update_config(self, **kwargs) -> None:
        """Update filter parameters at runtime."""
        for k, v in kwargs.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)
        # Rebuild One Euro filters with new params
        self._filter_x = _OneEuroFilter(
            min_cutoff=self._config.min_cutoff,
            beta=self._config.beta,
            dcutoff=self._config.dcutoff,
        )
        self._filter_y = _OneEuroFilter(
            min_cutoff=self._config.min_cutoff,
            beta=self._config.beta,
            dcutoff=self._config.dcutoff,
        )
