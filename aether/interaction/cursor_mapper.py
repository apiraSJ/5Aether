"""CursorMapper — maps hand input to stable cursor positions.

Combines CursorFilter (One Euro + dead zone) with:
    1. EMA smoothing (exponential moving average)
    2. Pinch anchor lock (stable position during pinch)
    3. Sensitivity control

Pipeline:
    HandController → CursorMapper → CursorController → InteractionController

Rules:
    - CursorMapper NEVER calls UI directly
    - CursorMapper ONLY produces (screen_x, screen_y) coordinates
    - During pinch: position is anchored to the pinch start point
    - During tracking: position follows filtered hand input
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from aether.interaction.cursor_filter import CursorFilter, FilterConfig


@dataclass
class MapperConfig:
    """Configuration for CursorMapper."""
    # EMA smoothing (0.0 = no smoothing, 1.0 = infinite smoothing)
    ema_alpha: float = 0.3

    # Dead zone in pixels (ignore small movements)
    dead_zone: float = 2.0

    # Sensitivity multiplier
    sensitivity: float = 1.0

    # Pinch anchor stability
    pinch_anchor_smoothing: float = 0.1  # Lower = more stable anchor

    # Screen dimensions
    screen_width: int = 1920
    screen_height: int = 1080


class CursorMapper:
    """Maps hand input to stable cursor positions.

    Combines One Euro filtering with EMA smoothing and pinch anchor lock.

    During TRACKING:
        Hand position → One Euro → EMA → Screen position

    During PINCH (click/drag):
        Pinch position → Anchor lock → Stable position
        (no jitter during interaction)

    Usage:
        mapper = CursorMapper(config)
        x, y = mapper.process(raw_x, raw_y, is_pinching=False)
    """

    def __init__(self, config: Optional[MapperConfig] = None) -> None:
        self._config = config or MapperConfig()

        # One Euro filter for adaptive smoothing
        filter_config = FilterConfig(
            min_cutoff=1.0,
            beta=0.5,
            dcutoff=1.0,
            dead_zone=self._config.dead_zone,
            sensitivity=self._config.sensitivity,
            mirror_x=True,
            screen_width=self._config.screen_width,
            screen_height=self._config.screen_height,
        )
        self._filter = CursorFilter(filter_config)

        # EMA state
        self._ema_x: Optional[float] = None
        self._ema_y: Optional[float] = None

        # Pinch anchor
        self._anchor_x: float = 0.0
        self._anchor_y: float = 0.0
        self._is_pinching: bool = False

        # Last output
        self._last_x: float = 0.0
        self._last_y: float = 0.0

    def process(
        self,
        raw_x: float,
        raw_y: float,
        is_pinching: bool = False,
    ) -> tuple[float, float]:
        """Process raw hand position into stable screen coordinates.

        Args:
            raw_x: Raw x from hand (0.0–1.0 normalized)
            raw_y: Raw y from hand (0.0–1.0 normalized)
            is_pinching: Whether pinch is currently active

        Returns:
            (screen_x, screen_y) in screen pixel coordinates.
        """
        # Filter through One Euro (includes dead zone, sensitivity, mirror)
        filtered_x, filtered_y = self._filter.process(raw_x, raw_y)

        if is_pinching and not self._is_pinching:
            # Pinch started — lock anchor to current position
            self._anchor_x = filtered_x
            self._anchor_y = filtered_y
            self._is_pinching = True

        elif not is_pinching and self._is_pinching:
            # Pinch ended — release anchor
            self._is_pinching = False

        if self._is_pinching:
            # During pinch: use anchor with minimal movement
            # Anchor moves very slowly to track large hand movements
            alpha = self._config.pinch_anchor_smoothing
            self._anchor_x = self._anchor_x * (1 - alpha) + filtered_x * alpha
            self._anchor_y = self._anchor_y * (1 - alpha) + filtered_y * alpha
            out_x = self._anchor_x
            out_y = self._anchor_y
        else:
            # During tracking: apply EMA smoothing
            out_x, out_y = self._apply_ema(filtered_x, filtered_y)

        self._last_x = out_x
        self._last_y = out_y
        return out_x, out_y

    def _apply_ema(self, x: float, y: float) -> tuple[float, float]:
        """Apply exponential moving average smoothing."""
        alpha = self._config.ema_alpha

        if self._ema_x is None:
            self._ema_x = x
            self._ema_y = y
        else:
            self._ema_x = self._ema_x * (1 - alpha) + x * alpha
            self._ema_y = self._ema_y * (1 - alpha) + y * alpha

        return self._ema_x, self._ema_y

    def reset(self) -> None:
        """Reset all filter state."""
        self._filter.reset()
        self._ema_x = None
        self._ema_y = None
        self._is_pinching = False
        self._anchor_x = 0.0
        self._anchor_y = 0.0
        self._last_x = 0.0
        self._last_y = 0.0

    def set_screen_size(self, width: int, height: int) -> None:
        """Update screen dimensions."""
        self._config.screen_width = width
        self._config.screen_height = height
        self._filter.update_config(screen_width=width, screen_height=height)

    @property
    def last_position(self) -> tuple[float, float]:
        return self._last_x, self._last_y

    @property
    def is_pinching(self) -> bool:
        return self._is_pinching
