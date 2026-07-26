"""
PointerEvent — the unified input event for all pointer-like interactions.

Per the ADR: mouse, hand tracking, XR controllers, and eye tracking all
produce PointerEvents. Widgets never know which input device produced the event.
This is the single abstraction that makes desktop, mobile, and XR share the
same interaction layer.

PointerEvent is a pure data structure — no behavior, no side effects.
It flows from InputAdapters through the EventBus to widgets.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class PointerEventType(Enum):
    """All possible pointer event types."""

    MOVE = auto()        # Pointer moved (includes hover)
    DOWN = auto()        # Button pressed (mouse click, hand pinch, XR trigger)
    UP = auto()          # Button released
    CLICK = auto()       # Down + Up in same widget within threshold
    DOUBLE_CLICK = auto()  # Two clicks in quick succession
    DRAG_START = auto()  # Move beyond threshold while pressed
    DRAG_MOVE = auto()   # Move while pressed (after DRAG_START)
    DRAG_END = auto()    # Up after DRAG_START
    SCROLL = auto()      # Scroll wheel or pinch zoom
    ENTER = auto()       # Pointer entered widget bounds
    LEAVE = auto()       # Pointer left widget bounds
    CANCEL = auto()      # Interaction cancelled (e.g., focus lost)


class PointerButton(Enum):
    """Which button/trigger is pressed."""

    NONE = 0
    PRIMARY = 1      # Left mouse, index pinch, main XR trigger
    SECONDARY = 2    # Right mouse, middle finger pinch, secondary XR trigger
    TERTIARY = 3     # Middle mouse, ring finger pinch
    BACK = 4         # Mouse back button, pinky pinch
    FORWARD = 5      # Mouse forward button


class InputDevice(Enum):
    """Source device for the pointer event."""

    MOUSE = "mouse"
    TOUCH = "touch"
    HAND_TRACKING = "hand_tracking"
    XR_CONTROLLER = "xr_controller"
    EYE_TRACKING = "eye_tracking"
    STYLUS = "stylus"


@dataclass(frozen=True, slots=True)
class PointerEvent:
    """Immutable pointer event — the universal input currency.

    Attributes:
        type:           What kind of pointer interaction occurred.
        x:              Normalized x position [0.0, 1.0] in viewport.
        y:              Normalized y position [0.0, 1.0] in viewport.
        button:         Which button/trigger is involved.
        device:         Which input device produced this event.
        modifiers:      Keyboard modifiers held (shift, ctrl, alt, meta).
        scroll_x:       Horizontal scroll delta (for SCROLL events).
        scroll_y:       Vertical scroll delta (for SCROLL events).
        pressure:       Pressure level [0.0, 1.0] if available (touch, stylus).
        tilt_x:         Tilt in degrees [-90, 90] if available (stylus).
        tilt_y:         Tilt in degrees [-90, 90] if available (stylus).
        twist:          Twist in degrees [0, 360] if available (stylus).
        id:             Unique event id for deduplication and correlation.
        timestamp:      Unix timestamp of event creation.
        device_id:      Identifier for the specific device instance.
        source:         Human-readable source label (e.g., "right_hand_index").
        confidence:     Detection confidence [0.0, 1.0] for hand/eye tracking.
    """

    type: PointerEventType
    x: float
    y: float
    button: PointerButton = PointerButton.NONE
    device: InputDevice = InputDevice.MOUSE
    modifiers: int = 0  # Bitmask: 1=Shift, 2=Ctrl, 4=Alt, 8=Meta
    scroll_x: float = 0.0
    scroll_y: float = 0.0
    pressure: float = 0.0
    tilt_x: float = 0.0
    tilt_y: float = 0.0
    twist: float = 0.0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    device_id: str = ""
    source: str = ""
    confidence: float = 1.0

    def __post_init__(self) -> None:
        # Validate coordinates are in normalized range
        if not (0.0 <= self.x <= 1.0):
            raise ValueError(f"PointerEvent.x must be in [0.0, 1.0], got {self.x}")
        if not (0.0 <= self.y <= 1.0):
            raise ValueError(f"PointerEvent.y must be in [0.0, 1.0], got {self.y}")

    @property
    def is_pressed(self) -> bool:
        """Whether a button is currently pressed (DOWN, DRAG_START, DRAG_MOVE)."""
        return self.type in (
            PointerEventType.DOWN,
            PointerEventType.DRAG_START,
            PointerEventType.DRAG_MOVE,
        )

    @property
    def is_drag(self) -> bool:
        """Whether this is a drag event."""
        return self.type in (
            PointerEventType.DRAG_START,
            PointerEventType.DRAG_MOVE,
            PointerEventType.DRAG_END,
        )

    @property
    def has_shift(self) -> bool:
        return bool(self.modifiers & 1)

    @property
    def has_ctrl(self) -> bool:
        return bool(self.modifiers & 2)

    @property
    def has_alt(self) -> bool:
        return bool(self.modifiers & 4)

    @property
    def has_meta(self) -> bool:
        return bool(self.modifiers & 8)

    @property
    def position_tuple(self) -> tuple[float, float]:
        """Return (x, y) as a tuple."""
        return (self.x, self.y)

    def with_type(self, new_type: PointerEventType) -> PointerEvent:
        """Return a copy with a different event type (frozen dataclass)."""
        return PointerEvent(
            type=new_type,
            x=self.x,
            y=self.y,
            button=self.button,
            device=self.device,
            modifiers=self.modifiers,
            scroll_x=self.scroll_x,
            scroll_y=self.scroll_y,
            pressure=self.pressure,
            tilt_x=self.tilt_x,
            tilt_y=self.tilt_y,
            twist=self.twist,
            timestamp=self.timestamp,
            device_id=self.device_id,
            source=self.source,
            confidence=self.confidence,
        )


# Modifier bitmask constants
MOD_SHIFT = 1
MOD_CTRL = 2
MOD_ALT = 4
MOD_META = 8


def create_mouse_move(x: float, y: float, modifiers: int = 0) -> PointerEvent:
    """Convenience: create a mouse move event."""
    return PointerEvent(
        type=PointerEventType.MOVE,
        x=x,
        y=y,
        device=InputDevice.MOUSE,
        modifiers=modifiers,
    )


def create_mouse_click(
    x: float, y: float, button: PointerButton = PointerButton.PRIMARY, modifiers: int = 0
) -> tuple[PointerEvent, PointerEvent]:
    """Convenience: create a DOWN + UP pair for a mouse click."""
    down = PointerEvent(
        type=PointerEventType.DOWN,
        x=x,
        y=y,
        button=button,
        device=InputDevice.MOUSE,
        modifiers=modifiers,
    )
    up = PointerEvent(
        type=PointerEventType.UP,
        x=x,
        y=y,
        button=button,
        device=InputDevice.MOUSE,
        modifiers=modifiers,
    )
    return (down, up)


def create_hand_pointer(
    x: float,
    y: float,
    hand_id: str = "right",
    is_pinching: bool = False,
    confidence: float = 1.0,
) -> PointerEvent:
    """Convenience: create a hand tracking pointer event."""
    event_type = PointerEventType.DOWN if is_pinching else PointerEventType.MOVE
    return PointerEvent(
        type=event_type,
        x=x,
        y=y,
        button=PointerButton.PRIMARY if is_pinching else PointerButton.NONE,
        device=InputDevice.HAND_TRACKING,
        source=f"{hand_id}_hand",
        confidence=confidence,
    )
