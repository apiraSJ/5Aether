"""InputRouter — routes raw input (mouse, hand, gesture) to InteractionController.

Central routing point for all input sources. Handles:
    - Mouse events → InteractionController
    - Hand tracking events → CursorController → InteractionController
    - Gesture events → InteractionController + CommandBus

Does NOT handle keyboard input (that goes to CLIWidget directly).
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Optional, Callable

from aether.interaction.interaction_controller import InteractionController
from aether.interaction.interaction_state import InteractionState
from aether.interaction.gestures import Gesture

logger = logging.getLogger("Aether.InputRouter")


class InputSource(Enum):
    """Origin of input event."""
    MOUSE = auto()
    HAND_TRACKING = auto()
    GESTURE = auto()
    CLI = auto()


class InputRouter:
    """Routes input events to the appropriate handler.

    All input sources go through this router:
        1. Mouse/Hand → CursorController (smoothing/filtering)
        2. CursorController → InteractionController (hit test, state machine)
        3. Gesture → InteractionController + CommandBus

    This ensures consistent interaction behavior regardless of input source.
    """

    def __init__(self, interaction_controller: InteractionController) -> None:
        self._ic = interaction_controller
        self._last_cursor_x: float = 0.0
        self._last_cursor_y: float = 0.0
        self._is_dragging: bool = False
        self._is_resizing: bool = False
        self._click_handlers: list[Callable] = []
        self._gesture_handlers: list[Callable] = []

    @property
    def interaction_controller(self) -> InteractionController:
        return self._ic

    def register_click_handler(self, handler: Callable) -> None:
        """Register a handler to be called when a click occurs.

        Handler receives: (panel_id: Optional[str], state: InteractionState)
        """
        self._click_handlers.append(handler)

    def register_gesture_handler(self, handler: Callable) -> None:
        """Register a handler to be called when a gesture occurs.

        Handler receives: (gesture: Gesture, x: float, y: float, confidence: float)
        """
        self._gesture_handlers.append(handler)

    def on_mouse_move(self, x: float, y: float) -> None:
        """Handle mouse move event."""
        self._last_cursor_x = x
        self._last_cursor_y = y
        self._ic.on_cursor_move(x, y)

    def on_mouse_press(self, x: float, y: float) -> Optional[str]:
        """Handle mouse press (left button).

        Returns panel_id if a panel was clicked.
        """
        self._last_cursor_x = x
        self._last_cursor_y = y

        # If we have a selected panel and mouse is pressed, start drag
        if self._ic.state == InteractionState.SELECTED:
            # Check if on resize handle
            if (self._ic.hover_result and self._ic.hover_result.is_resize_handle):
                self._is_resizing = self._ic.on_resize_start(x, y)
                return None

            # Start drag
            self._is_dragging = self._ic.on_drag_start(x, y)
            if self._is_dragging:
                return None

        # Otherwise, do click handling (select panel)
        result = self._ic.on_click(x, y)
        self._notify_click(result, self._ic.state)
        return result

    def on_mouse_release(self, x: float, y: float) -> Optional[str]:
        """Handle mouse release.

        Returns panel_id if drag/resize ended.
        """
        self._last_cursor_x = x
        self._last_cursor_y = y

        if self._is_dragging:
            self._is_dragging = False
            return self._ic.on_drag_end()

        if self._is_resizing:
            self._is_resizing = False
            return self._ic.on_resize_end()

        return None

    def on_hand_move(self, x: float, y: float) -> None:
        """Handle hand tracking move event."""
        self._last_cursor_x = x
        self._last_cursor_y = y
        self._ic.on_cursor_move(x, y)

    def on_hand_pinch_start(self, x: float, y: float) -> Optional[str]:
        """Handle hand pinch start (equivalent to mouse press)."""
        self._last_cursor_x = x
        self._last_cursor_y = y

        if self._ic.state == InteractionState.SELECTED:
            if (self._ic.hover_result and self._ic.hover_result.is_resize_handle):
                self._is_resizing = self._ic.on_resize_start(x, y)
                return None
            self._is_dragging = self._ic.on_drag_start(x, y)
            if self._is_dragging:
                return None

        result = self._ic.on_click(x, y)
        self._notify_click(result, self._ic.state)
        return result

    def on_hand_pinch_end(self, x: float, y: float) -> Optional[str]:
        """Handle hand pinch end (equivalent to mouse release)."""
        self._last_cursor_x = x
        self._last_cursor_y = y

        if self._is_dragging:
            self._is_dragging = False
            return self._ic.on_drag_end()

        if self._is_resizing:
            self._is_resizing = False
            return self._ic.on_resize_end()

        return None

    def on_hand_gesture(
        self,
        gesture: Gesture,
        x: float,
        y: float,
        confidence: float = 1.0,
        hand_label: str = "Right",
    ) -> None:
        """Handle any hand gesture through the unified pipeline.

        All gestures go through InputRouter for consistent behavior:
        - PINCH: drag/click (handled by on_hand_pinch_start/end)
        - OPEN_PALM: cursor tracking (handled by on_hand_move)
        - Other gestures: routed to CommandBus via GesturePlugin

        This method:
        1. Updates cursor position for all gestures
        2. For PINCH, delegates to pinch start/end
        3. For other gestures, notifies gesture handlers

        Args:
            gesture: Canonical Gesture enum
            x, y: Cursor position
            confidence: Gesture confidence
            hand_label: "Left" or "Right"
        """
        # Always update cursor position
        self._last_cursor_x = x
        self._last_cursor_y = y
        self._ic.on_cursor_move(x, y)

        # Handle pinch gestures through existing pinch flow
        if gesture == Gesture.PINCH:
            # Check if we're starting or ending a pinch
            is_pinching = True  # This is called on each frame with pinch
            # Note: Pinch state tracking happens in GesturePlugin
            # Here we just update cursor position
            return

        # For non-pinch gestures, notify handlers
        self._notify_gesture(gesture, x, y, confidence)

    def on_gesture(self, gesture_name: str, confidence: float = 1.0) -> None:
        """Handle detected gesture (legacy string-based).

        Routes to CommandBus via InteractionController.
        Gesture mapping is configured in config/gesture.yaml.
        This method is a pass-through; actual command dispatch
        happens in GesturePlugin which has CommandBus access.
        """
        logger.debug("Gesture detected: %s (%.2f)", gesture_name, confidence)

    def cancel(self) -> None:
        """Cancel current interaction (e.g., on ESC key)."""
        self._is_dragging = False
        self._is_resizing = False
        self._ic.on_cancel()

    # ── Internal ───────────────────────────────────────────────────

    def _notify_click(self, panel_id: Optional[str], state: InteractionState) -> None:
        for handler in self._click_handlers:
            try:
                handler(panel_id, state)
            except Exception as e:
                logger.warning("Click handler error: %s", e)

    def _notify_gesture(self, gesture: Gesture, x: float, y: float, confidence: float) -> None:
        for handler in self._gesture_handlers:
            try:
                handler(gesture, x, y, confidence)
            except Exception as e:
                logger.warning("Gesture handler error: %s", e)
