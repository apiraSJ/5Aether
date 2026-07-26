"""Virtual cursor implementation with drag-and-drop support.

Architecture:
    CursorPlugin (vision input) → VisionEventAdapter → CursorEvent → IntentResolver → CursorCommand → EventBus → CursorWidget

Cursor events flow through EventBus only, not directly to command handlers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from aether.core.command import Command
from aether.core.service import IService

logger = logging.getLogger("Aether.VirtualCursor")


class CursorState(Enum):
    """Virtual cursor state."""
    IDLE = "idle"
    DRAG_START = "drag_start"
    DRAGGING = "dragging"
    DRAG_END = "drag_end"


@dataclass
class CursorPosition:
    """Normalized cursor position in [0,1] coordinates."""
    x: float = 0.5
    y: float = 0.5
    screen_x: int = 960
    screen_y: int = 540


@dataclass
class DropTarget:
    """Object that can receive drop actions."""
    id: str
    name: str
    bounds: list[int]  # [x1, y1, x2, y2]
    can_drop: bool = True


class VirtualCursor(IService):
    """Virtual cursor service with drag-and-drop support.

    Data flow:
        CursorEvent → VirtualCursor → CursorCommand → CommandBus → UI Update
    """

    name = "virtual_cursor"

    def __init__(self) -> None:
        self._position = CursorPosition()
        self._drag_start_pos = CursorPosition()
        self._dragging = False
        self._drag_target: DropTarget | None = None
        self._command_bus = None
        self._event_bus = None
        self._update_cb = None

    def initialize(self, event_bus, command_bus) -> None:
        self._event_bus = event_bus
        self._command_bus = command_bus

        # Subscribe to cursor events from VisionEventAdapter
        self._event_bus.subscribe(
            "vision.cursor.moved",
            lambda e: self._on_cursor_moved(e)
        )
        self._event_bus.subscribe(
            "vision.gesture.holding",
            lambda e: self._on_gesture_holding(e)
        )
        self._event_bus.subscribe(
            "vision.gesture.ended",
            lambda e: self._on_gesture_ended(e)
        )

    def update_position(self, x: float, y: float, screen_w: int = 1920, screen_h: int = 1080) -> None:
        """Update cursor position from hand tracking."""
        self._position.x = max(0.0, min(1.0, x))
        self._position.y = max(0.0, min(1.0, y))
        self._position.screen_x = int(self._position.x * screen_w)
        self._position.screen_y = int(self._position.y * screen_h)

    def set_drag_state(self, state: CursorState, target: DropTarget | None = None) -> None:
        """Update drag state."""
        if state == CursorState.DRAG_START:
            self._dragging = True
            self._drag_start_pos = CursorPosition(
                x=self._position.x,
                y=self._position.y,
                screen_x=self._position.screen_x,
                screen_y=self._position.screen_y
            )
            self._drag_target = target
        elif state == CursorState.DRAG_END:
            self._dragging = False
            self._drag_target = None

        self._dispatch_cursor_command(state, target)

    def _dispatch_cursor_command(self, state: CursorState, target: DropTarget | None) -> None:
        """Emit command through CommandBus, not EventBus directly."""
        if self._command_bus:
            cmd_name = {
                CursorState.IDLE: "cursor_idle",
                CursorState.DRAG_START: "cursor_drag_start",
                CursorState.DRAGGING: "cursor_dragging",
                CursorState.DRAG_END: "cursor_drag_end",
            }[state]

            params = {
                "position": {
                    "x": self._position.x,
                    "y": self._position.y,
                    "screen_x": self._position.screen_x,
                    "screen_y": self._position.screen_y,
                },
                "drag_target": target.__dict__ if target else None,
                "drag_start": {
                    "x": self._drag_start_pos.x,
                    "y": self._drag_start_pos.y,
                }
                if state == CursorState.DRAG_END
                else None,
            }

            self._command_bus.dispatch(Command(name=cmd_name, source="virtual_cursor", params=params))

    def _on_cursor_moved(self, event) -> None:
        self.update_position(
            event.payload.get("x", 0.5),
            event.payload.get("y", 0.5),
            event.payload.get("screen_width", 1920),
            event.payload.get("screen_height", 1080),
        )

    def _on_gesture_holding(self, event) -> None:
        # For gesture holding, we assume it's a drag start
        self.set_drag_state(CursorState.DRAG_START, None)

    def _on_gesture_ended(self, event) -> None:
        # For gesture ended, we assume it's a drag end
        self.set_drag_state(CursorState.DRAG_END, None)
