"""OverlayModel — single source of truth for all vision overlay state.

Architecture:
    EventBus → OverlayController → OverlayModel → Widgets (read-only)

Widgets never subscribe to events. They paint from this model.
Model is updated by OverlayController when events arrive.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CursorState(Enum):
    """Visual cursor indicator state."""
    DEFAULT = "default"
    HOVER = "hover"
    PINCH = "pinch"
    DRAG_START = "drag_start"
    DRAGGING = "dragging"
    DRAG_END = "drag_end"


class GesturePhase(Enum):
    """Gesture lifecycle phase."""
    NONE = "none"
    STARTED = "started"
    HOLDING = "holding"
    ENDED = "ended"


@dataclass
class DetectedObject:
    """A single detected object with spatial info."""
    id: str
    name: str
    box: list[int] = field(default_factory=lambda: [0, 0, 0, 0])
    confidence: float = 0.0
    distance: float = 0.0
    selected: bool = False
    hovered: bool = False
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


@dataclass
class DetectedHand:
    """A detected hand with landmarks and gesture."""
    label: str = "Unknown"
    landmarks: list[dict] = field(default_factory=list)
    gesture: str = "Unknown"
    gesture_score: float = 0.0
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)


@dataclass
class CursorPosition:
    """Cursor position in normalized [0,1] coordinates."""
    x: float = 0.5
    y: float = 0.5
    state: CursorState = CursorState.DEFAULT
    visible: bool = False
    drag_target: str = ""
    selection_glow: bool = False


@dataclass
class GestureInfo:
    """Current gesture state."""
    name: str = "Unknown"
    phase: GesturePhase = GesturePhase.NONE
    confidence: float = 0.0
    hand: str = "Unknown"
    start_time: float = 0.0
    duration: float = 0.0


@dataclass
class SceneInfo:
    """Overall scene state."""
    object_count: int = 0
    hand_count: int = 0
    tracking: bool = True
    camera_active: bool = False
    fps: float = 0.0
    ai_ready: bool = False


class OverlayModel:
    """Thread-safe overlay state. Widgets read from this.

    Updated by OverlayController on event callbacks.
    All methods are safe to call from the Qt main thread.
    """

    def __init__(self) -> None:
        self._objects: dict[str, DetectedObject] = {}
        self._hands: list[DetectedHand] = []
        self._cursor: CursorPosition = CursorPosition()
        self._gesture: GestureInfo = GestureInfo()
        self._scene: SceneInfo = SceneInfo()
        self._notifications: list[tuple[str, float]] = []  # (text, timestamp)
        self._event_history: deque[dict] = deque(maxlen=200)  # (timestamp, source, type)
        self._dirty: bool = True

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_clean(self) -> None:
        self._dirty = False

    # ── Objects ─────────────────────────────────────────────────────

    def update_objects(self, objects: list[dict]) -> None:
        """Replace object list from YOLO detection."""
        now = time.time()
        new_map: dict[str, DetectedObject] = {}

        for obj in objects:
            oid = obj.get("name", "unknown")
            new_map[oid] = DetectedObject(
                id=oid,
                name=oid,
                box=obj.get("box", [0, 0, 0, 0]),
                confidence=obj.get("conf", 0.0),
                distance=obj.get("distance_z", 0.0),
                selected=self._objects.get(oid, DetectedObject(id=oid, name=oid)).selected,
                hovered=self._objects.get(oid, DetectedObject(id=oid, name=oid)).hovered,
                first_seen=self._objects.get(oid, DetectedObject(id=oid, name=oid)).first_seen,
                last_seen=now,
            )

        self._objects = new_map
        self._scene.object_count = len(self._objects)
        self._dirty = True

    def select_object(self, oid: str) -> None:
        for obj in self._objects.values():
            obj.selected = (obj.id == oid)
        self._dirty = True

    def hover_object(self, oid: str) -> None:
        for obj in self._objects.values():
            obj.hovered = (obj.id == oid)
        self._dirty = True

    @property
    def objects(self) -> list[DetectedObject]:
        return list(self._objects.values())

    # ── Hands ───────────────────────────────────────────────────────

    def update_hands(self, hands: list[dict]) -> None:
        """Replace hand list from MediaPipe."""
        now = time.time()
        self._hands = [
            DetectedHand(
                label=h.get("label", "Unknown"),
                landmarks=h.get("landmarks", []),
                gesture=h.get("gesture", "Unknown"),
                gesture_score=h.get("gesture_score", 0.0),
                last_seen=now,
            )
            for h in hands
        ]
        self._scene.hand_count = len(self._hands)
        self._dirty = True

    @property
    def hands(self) -> list[DetectedHand]:
        return list(self._hands)

    # ── Cursor ──────────────────────────────────────────────────────

    def update_cursor(self, x: float, y: float, state: CursorState = CursorState.DEFAULT) -> None:
        self._cursor.x = x
        self._cursor.y = y
        self._cursor.state = state
        self._cursor.visible = True
        self._dirty = True

    def update_cursor_state(self, state: CursorState, drag_target: str = "", selection_glow: bool = False) -> None:
        """Update cursor visual state (drag, hover, etc.)."""
        self._cursor.state = state
        if drag_target:
            self._cursor.drag_target = drag_target
        self._cursor.selection_glow = selection_glow
        self._dirty = True

    def clear_selection_glow(self) -> None:
        """Clear cursor selection glow after animation."""
        self._cursor.selection_glow = False
        self._dirty = True

    def hide_cursor(self) -> None:
        self._cursor.visible = False
        self._dirty = True

    @property
    def cursor(self) -> CursorPosition:
        return self._cursor

    # ── Gesture ─────────────────────────────────────────────────────

    def update_gesture(self, name: str, phase: GesturePhase, confidence: float, hand: str) -> None:
        self._gesture.name = name
        self._gesture.phase = phase
        self._gesture.confidence = confidence
        self._gesture.hand = hand
        if phase == GesturePhase.STARTED:
            self._gesture.start_time = time.time()
        self._gesture.duration = time.time() - self._gesture.start_time if self._gesture.start_time else 0.0
        self._dirty = True

    def clear_gesture(self) -> None:
        self._gesture = GestureInfo()
        self._dirty = True

    @property
    def gesture(self) -> GestureInfo:
        return self._gesture

    # ── Scene ───────────────────────────────────────────────────────

    def update_scene(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if hasattr(self._scene, k):
                setattr(self._scene, k, v)
        self._dirty = True

    @property
    def scene(self) -> SceneInfo:
        return self._scene

    # ── Event History ──────────────────────────────────────────────

    def append_event(self, timestamp: str, source: str, event_type: str) -> None:
        """Add an event to the history log for developer timeline."""
        self._event_history.append({"ts": timestamp, "src": source, "type": event_type})

    @property
    def event_history(self) -> list[dict]:
        return list(self._event_history)

    # ── Notifications ───────────────────────────────────────────────

    def push_notification(self, text: str, ttl: float = 3.0) -> None:
        self._notifications.append((text, time.time() + ttl))
        self._dirty = True

    @property
    def notifications(self) -> list[str]:
        now = time.time()
        self._notifications = [(t, exp) for t, exp in self._notifications if exp > now]
        return [t for t, _ in self._notifications]

    # ── Reset ───────────────────────────────────────────────────────

    def clear(self) -> None:
        self._objects.clear()
        self._hands.clear()
        self._cursor = CursorPosition()
        self._gesture = GestureInfo()
        self._scene = SceneInfo()
        self._notifications.clear()
        self._event_history.clear()
        self._dirty = True
