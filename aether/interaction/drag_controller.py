"""DragController — handles panel drag with geometry tracking.

Flow:
    Pinch start → Capture panel → Store initial geometry
    Move hand → Calculate delta → Update PanelRegistry
    Release → Emit PANEL_MOVED → Mark layout dirty

Do NOT save layout every frame. Save only on release or manual save.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from aether.ui.panel.panel_registry import PanelRegistry

logger = logging.getLogger("Aether.DragController")


@dataclass
class DragState:
    """Current drag operation state."""

    active: bool = False
    panel_id: str = ""
    start_x: float = 0.0
    start_y: float = 0.0
    panel_start_x: float = 0.0
    panel_start_y: float = 0.0
    current_x: float = 0.0
    current_y: float = 0.0
    dirty: bool = False

    @property
    def delta_x(self) -> float:
        return self.current_x - self.start_x

    @property
    def delta_y(self) -> float:
        return self.current_y - self.start_y

    @property
    def panel_x(self) -> float:
        return self.panel_start_x + self.delta_x

    @property
    def panel_y(self) -> float:
        return self.panel_start_y + self.delta_y


class DragController:
    """Handles panel drag operations.

    Captures the panel and initial geometry on drag start,
    updates geometry during drag, and finalizes on drag end.
    """

    def __init__(self, panel_registry: PanelRegistry) -> None:
        self._registry = panel_registry
        self._state = DragState()

    @property
    def state(self) -> DragState:
        return self._state

    @property
    def is_dragging(self) -> bool:
        return self._state.active

    @property
    def is_dirty(self) -> bool:
        return self._state.dirty

    def start(self, panel_id: str, cursor_x: float, cursor_y: float) -> bool:
        """Start dragging a panel.

        Args:
            panel_id: Panel to drag
            cursor_x: Current cursor x
            cursor_y: Current cursor y

        Returns:
            True if drag started successfully.
        """
        info = self._registry.get(panel_id)
        if not info:
            return False

        self._state = DragState(
            active=True,
            panel_id=panel_id,
            start_x=cursor_x,
            start_y=cursor_y,
            panel_start_x=float(info.x),
            panel_start_y=float(info.y),
            current_x=cursor_x,
            current_y=cursor_y,
            dirty=False,
        )

        logger.debug("Drag start: '%s' from (%.0f, %.0f)", panel_id, cursor_x, cursor_y)
        return True

    def update(self, cursor_x: float, cursor_y: float) -> Optional[tuple[float, float]]:
        """Update drag position. Returns new (x, y) for the panel.

        Does NOT update PanelRegistry — caller decides when to apply.
        """
        if not self._state.active:
            return None

        self._state.current_x = cursor_x
        self._state.current_y = cursor_y

        new_x = self._state.panel_x
        new_y = self._state.panel_y
        return new_x, new_y

    def apply(self) -> bool:
        """Apply current drag position to PanelRegistry.

        Returns True if applied.
        """
        if not self._state.active:
            return False

        new_x = int(self._state.panel_x)
        new_y = int(self._state.panel_y)
        self._registry.move_panel(self._state.panel_id, new_x, new_y)
        self._state.dirty = True
        return True

    def end(self) -> Optional[str]:
        """End drag operation. Returns the panel_id that was dragged.

        Applies final position and marks layout dirty.
        """
        if not self._state.active:
            return None

        panel_id = self._state.panel_id
        self.apply()

        logger.debug("Drag end: '%s' at (%.0f, %.0f)",
                      panel_id, self._state.panel_x, self._state.panel_y)

        self._state.active = False
        return panel_id

    def cancel(self) -> None:
        """Cancel drag and restore original position."""
        if not self._state.active:
            return

        self._registry.move_panel(
            self._state.panel_id,
            int(self._state.panel_start_x),
            int(self._state.panel_start_y),
        )
        self._state.active = False
        logger.debug("Drag cancelled: '%s'", self._state.panel_id)
