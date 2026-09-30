"""CursorController — manages cursor state during interaction.

States:
    TRACKING: index finger controls cursor (normal)
    FROZEN: cursor position locked (during click)
    GRABBING: movement controls selected panel (drag)

Freeze is temporary — only during click action.
Do NOT permanently lock cursor.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from aether.interaction.interaction_state import CursorMode

logger = logging.getLogger("Aether.CursorController")


@dataclass
class CursorPosition:
    """Cursor position in screen coordinates."""

    x: float = 0.0
    y: float = 0.0
    timestamp: float = 0.0


class CursorController:
    """Manages cursor behavior during interaction.

    Controls when cursor is tracking, frozen, or grabbing.
    Freezing is temporary — used during click action to prevent jitter.
    """

    def __init__(self, freeze_duration_ms: float = 100.0) -> None:
        self._mode = CursorMode.TRACKING
        self._position = CursorPosition()
        self._frozen_position: Optional[CursorPosition] = None
        self._freeze_start: float = 0.0
        self._freeze_duration = freeze_duration_ms / 1000.0
        self._grab_offset_x: float = 0.0
        self._grab_offset_y: float = 0.0

    @property
    def mode(self) -> CursorMode:
        return self._mode

    @property
    def position(self) -> CursorPosition:
        if self._mode == CursorMode.FROZEN and self._frozen_position:
            return self._frozen_position
        return self._position

    @property
    def is_tracking(self) -> bool:
        return self._mode == CursorMode.TRACKING

    @property
    def is_frozen(self) -> bool:
        return self._mode == CursorMode.FROZEN

    @property
    def is_grabbing(self) -> bool:
        return self._mode == CursorMode.GRABBING

    def update(self, x: float, y: float) -> Optional[tuple[float, float]]:
        """Update cursor position from filtered input.

        Returns (x, y) to use, or None if cursor is frozen/grabbing
        and the raw input should be ignored.
        """
        now = time.perf_counter()

        if self._mode == CursorMode.FROZEN:
            # Check if freeze expired
            if (now - self._freeze_start) >= self._freeze_duration:
                self._unfreeze()
                # Fall through to normal tracking
            else:
                return None  # Ignore input during freeze

        if self._mode == CursorMode.GRABBING:
            # In grabbing mode, return the raw position
            # (caller uses delta for panel movement)
            self._position = CursorPosition(x=x, y=y, timestamp=now)
            return x, y

        # TRACKING mode
        self._position = CursorPosition(x=x, y=y, timestamp=now)
        return x, y

    def freeze(self, x: Optional[float] = None, y: Optional[float] = None) -> None:
        """Freeze cursor at current or specified position.

        Used during click to prevent jitter.
        Auto-unfreezes after freeze_duration.
        """
        if x is not None and y is not None:
            self._frozen_position = CursorPosition(x=x, y=y, timestamp=time.perf_counter())
        else:
            self._frozen_position = CursorPosition(
                x=self._position.x, y=self._position.y, timestamp=time.perf_counter()
            )
        self._freeze_start = time.perf_counter()
        self._mode = CursorMode.FROZEN
        logger.debug("Cursor frozen at (%.1f, %.1f)", self._frozen_position.x, self._frozen_position.y)

    def unfreeze(self) -> None:
        """Manually unfreeze cursor."""
        self._unfreeze()

    def _unfreeze(self) -> None:
        if self._mode == CursorMode.FROZEN:
            self._mode = CursorMode.TRACKING
            self._frozen_position = None
            logger.debug("Cursor unfrozen")

    def start_grab(self, panel_x: float, panel_y: float) -> None:
        """Start grabbing mode. Records offset between cursor and panel.

        Args:
            panel_x: Panel's current x position
            panel_y: Panel's current y position
        """
        self._grab_offset_x = self._position.x - panel_x
        self._grab_offset_y = self._position.y - panel_y
        self._mode = CursorMode.GRABBING
        logger.debug("Cursor grab started (offset: %.1f, %.1f)", self._grab_offset_x, self._grab_offset_y)

    def end_grab(self) -> tuple[float, float]:
        """End grabbing mode. Returns the grab offset.

        Returns:
            (offset_x, offset_y) — the initial offset between cursor and panel.
        """
        offset = (self._grab_offset_x, self._grab_offset_y)
        self._mode = CursorMode.TRACKING
        self._grab_offset_x = 0.0
        self._grab_offset_y = 0.0
        logger.debug("Cursor grab ended")
        return offset

    @property
    def grab_offset(self) -> tuple[float, float]:
        return self._grab_offset_x, self._grab_offset_y
