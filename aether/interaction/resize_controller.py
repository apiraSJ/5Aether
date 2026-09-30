"""ResizeController — handles panel resize with min/max constraints.

Supports bottom-right corner resize via pinch.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from aether.ui.panel.panel_registry import PanelRegistry

logger = logging.getLogger("Aether.ResizeController")


@dataclass
class ResizeHandle:
    """Identifies a resize handle position."""

    NONE = "none"
    BOTTOM_RIGHT = "bottom_right"
    BOTTOM_LEFT = "bottom_left"
    TOP_RIGHT = "top_right"
    TOP_LEFT = "top_left"


@dataclass
class ResizeState:
    """Current resize operation state."""

    active: bool = False
    panel_id: str = ""
    handle: str = ResizeHandle.NONE
    start_x: float = 0.0
    start_y: float = 0.0
    panel_start_w: int = 0
    panel_start_h: int = 0
    panel_start_x: int = 0
    panel_start_y: int = 0
    current_x: float = 0.0
    current_y: float = 0.0
    min_width: int = 200
    min_height: int = 100
    max_width: int = 2000
    max_height: int = 1500


class ResizeController:
    """Handles panel resize operations.

    Captures the panel and initial size on resize start,
    applies min/max constraints during resize,
    and finalizes on resize end.
    """

    def __init__(
        self,
        panel_registry: PanelRegistry,
        min_width: int = 200,
        min_height: int = 100,
        max_width: int = 2000,
        max_height: int = 1500,
    ) -> None:
        self._registry = panel_registry
        self._min_w = min_width
        self._min_h = min_height
        self._max_w = max_width
        self._max_h = max_height
        self._state = ResizeState(
            min_width=min_width,
            min_height=min_height,
            max_width=max_width,
            max_height=max_height,
        )

    @property
    def state(self) -> ResizeState:
        return self._state

    @property
    def is_resizing(self) -> bool:
        return self._state.active

    def start(self, panel_id: str, cursor_x: float, cursor_y: float) -> bool:
        """Start resizing a panel from its bottom-right corner."""
        info = self._registry.get(panel_id)
        if not info:
            return False

        self._state = ResizeState(
            active=True,
            panel_id=panel_id,
            handle=ResizeHandle.BOTTOM_RIGHT,
            start_x=cursor_x,
            start_y=cursor_y,
            panel_start_w=info.w,
            panel_start_h=info.h,
            panel_start_x=info.x,
            panel_start_y=info.y,
            current_x=cursor_x,
            current_y=cursor_y,
            min_width=self._min_w,
            min_height=self._min_h,
            max_width=self._max_w,
            max_height=self._max_h,
        )

        logger.debug("Resize start: '%s'", panel_id)
        return True

    def update(self, cursor_x: float, cursor_y: float) -> Optional[tuple[int, int]]:
        """Update resize. Returns new (width, height) for the panel."""
        if not self._state.active:
            return None

        self._state.current_x = cursor_x
        self._state.current_y = cursor_y

        dx = cursor_x - self._state.start_x
        dy = cursor_y - self._state.start_y

        new_w = max(self._state.min_width, min(self._state.max_width,
                     int(self._state.panel_start_w + dx)))
        new_h = max(self._state.min_height, min(self._state.max_height,
                     int(self._state.panel_start_h + dy)))

        return new_w, new_h

    def apply(self) -> bool:
        """Apply current resize to PanelRegistry."""
        if not self._state.active:
            return False

        dx = self._state.current_x - self._state.start_x
        dy = self._state.current_y - self._state.start_y

        new_w = max(self._state.min_width, min(self._state.max_width,
                     int(self._state.panel_start_w + dx)))
        new_h = max(self._state.min_height, min(self._state.max_height,
                     int(self._state.panel_start_h + dy)))

        self._registry.resize_panel(self._state.panel_id, new_w, new_h)
        return True

    def end(self) -> Optional[str]:
        """End resize. Returns panel_id."""
        if not self._state.active:
            return None

        panel_id = self._state.panel_id
        self.apply()

        logger.debug("Resize end: '%s' (%d×%d)", panel_id,
                      self._state.panel_start_w, self._state.panel_start_h)

        self._state.active = False
        return panel_id

    def cancel(self) -> None:
        """Cancel resize and restore original size."""
        if not self._state.active:
            return

        self._registry.resize_panel(
            self._state.panel_id,
            self._state.panel_start_w,
            self._state.panel_start_h,
        )
        self._state.active = False
        logger.debug("Resize cancelled: '%s'", self._state.panel_id)
