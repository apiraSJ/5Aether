"""OverlayController — subscribes to vision events, updates OverlayModel.

Architecture:
    EventBus → OverlayController → OverlayModel → Widgets (read-only)

This controller is the ONLY component that touches both EventBus and OverlayModel.
Widgets never see EventBus events.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from aether.core.event_bus_v2 import Event

if TYPE_CHECKING:
    from aether.ui.overlay_model import OverlayModel

logger = logging.getLogger("Aether.OverlayController")


class OverlayController:
    """Bridges EventBus events to OverlayModel state.

    Subscribes to all vision events and updates the model accordingly.
    Widgets read from the model and never touch the bus.
    """

    def __init__(self, event_bus, model: OverlayModel) -> None:
        self._event_bus = event_bus
        self._model = model
        self._frame_count = 0
        self._last_fps_time = time.time()
        self._fps = 0.0
        self._log_handler = self._make_log_handler()
        self._subscribe()

    def _make_log_handler(self):
        def _log(event: Event) -> None:
            ts = time.strftime("%H:%M:%S")
            etype = event.type.value if hasattr(event.type, 'value') else str(event.type)
            self._model.append_event(ts, event.source or "?", etype)
        return _log

    def _subscribe(self) -> None:
        """Register event handlers."""
        bus = self._event_bus
        topics = [
            "vision.object.detected", "vision.object.tracked", "vision.object.lost",
            "vision.hand.detected", "vision.hand.updated", "vision.hand.lost",
            "vision.cursor.moved",
            "vision.gesture.started", "vision.gesture.holding", "vision.gesture.ended",
            "vision.frame.ready", "vision.camera.started", "vision.camera.stopped",
            "vision.tracking.lost", "vision.tracking.recovered",
            "notification.show",
            "cursor.drag_start", "cursor.drag_end", "cursor.draggable", "cursor.idle",
        ]
        for topic in topics:
            bus.subscribe(topic, self._log_handler)
        bus.subscribe("vision.object.detected", self._on_object_detected)
        bus.subscribe("vision.object.tracked", self._on_object_tracked)
        bus.subscribe("vision.object.lost", self._on_object_lost)
        bus.subscribe("vision.hand.detected", self._on_hand_detected)
        bus.subscribe("vision.hand.updated", self._on_hand_updated)
        bus.subscribe("vision.hand.lost", self._on_hand_lost)
        bus.subscribe("vision.cursor.moved", self._on_cursor_moved)
        bus.subscribe("vision.gesture.started", self._on_gesture_started)
        bus.subscribe("vision.gesture.holding", self._on_gesture_holding)
        bus.subscribe("vision.gesture.ended", self._on_gesture_ended)
        bus.subscribe("vision.frame.ready", self._on_frame_ready)
        bus.subscribe("vision.camera.started", self._on_camera_started)
        bus.subscribe("vision.camera.stopped", self._on_camera_stopped)
        bus.subscribe("vision.tracking.lost", self._on_tracking_lost)
        bus.subscribe("vision.tracking.recovered", self._on_tracking_recovered)
        bus.subscribe("notification.show", self._on_notification)
        bus.subscribe("cursor.drag_start", self._on_cursor_drag_start)
        bus.subscribe("cursor.drag_end", self._on_cursor_drag_end)
        bus.subscribe("cursor.draggable", self._on_cursor_draggable)
        bus.subscribe("cursor.idle", self._on_cursor_idle)
        logger.info("OverlayController subscribed to vision events")

    def unsubscribe(self) -> None:
        """Remove all event handlers."""
        bus = self._event_bus
        topics = [
            "vision.object.detected", "vision.object.tracked", "vision.object.lost",
            "vision.hand.detected", "vision.hand.updated", "vision.hand.lost",
            "vision.cursor.moved",
            "vision.gesture.started", "vision.gesture.holding", "vision.gesture.ended",
            "vision.frame.ready", "vision.camera.started", "vision.camera.stopped",
            "vision.tracking.lost", "vision.tracking.recovered",
            "notification.show",
            "cursor.drag_start", "cursor.drag_end", "cursor.draggable", "cursor.idle",
        ]
        for topic in topics:
            bus.unsubscribe(topic, self._log_handler)
        bus.unsubscribe("vision.object.detected", self._on_object_detected)
        bus.unsubscribe("vision.object.tracked", self._on_object_tracked)
        bus.unsubscribe("vision.object.lost", self._on_object_lost)
        bus.unsubscribe("vision.hand.detected", self._on_hand_detected)
        bus.unsubscribe("vision.hand.updated", self._on_hand_updated)
        bus.unsubscribe("vision.hand.lost", self._on_hand_lost)
        bus.unsubscribe("vision.cursor.moved", self._on_cursor_moved)
        bus.unsubscribe("vision.gesture.started", self._on_gesture_started)
        bus.unsubscribe("vision.gesture.holding", self._on_gesture_holding)
        bus.unsubscribe("vision.gesture.ended", self._on_gesture_ended)
        bus.unsubscribe("vision.frame.ready", self._on_frame_ready)
        bus.unsubscribe("vision.camera.started", self._on_camera_started)
        bus.unsubscribe("vision.camera.stopped", self._on_camera_stopped)
        bus.unsubscribe("vision.tracking.lost", self._on_tracking_lost)
        bus.unsubscribe("vision.tracking.recovered", self._on_tracking_recovered)
        bus.unsubscribe("notification.show", self._on_notification)
        bus.unsubscribe("cursor.drag_start", self._on_cursor_drag_start)
        bus.unsubscribe("cursor.drag_end", self._on_cursor_drag_end)
        bus.unsubscribe("cursor.draggable", self._on_cursor_draggable)
        bus.unsubscribe("cursor.idle", self._on_cursor_idle)

    # ── Object events ───────────────────────────────────────────────

    def _on_object_detected(self, event: Event) -> None:
        objects = event.payload.get("objects", [])
        self._model.update_objects(objects)

    def _on_object_tracked(self, event: Event) -> None:
        objects = event.payload.get("objects", [])
        self._model.update_objects(objects)

    def _on_object_lost(self, event: Event) -> None:
        name = event.payload.get("name", "")
        if name:
            self._model.update_objects([
                o.__dict__ for o in self._model.objects if o.id != name
            ])

    # ── Hand events ─────────────────────────────────────────────────

    def _on_hand_detected(self, event: Event) -> None:
        hands = event.payload.get("hands", [])
        self._model.update_hands(hands)

    def _on_hand_updated(self, event: Event) -> None:
        hands = event.payload.get("hands", [])
        self._model.update_hands(hands)

    def _on_hand_lost(self, event: Event) -> None:
        label = event.payload.get("label", "")
        self._model.update_hands([
            h.__dict__ for h in self._model.hands if h.label != label
        ])

    # ── Cursor events ───────────────────────────────────────────────

    def _on_cursor_moved(self, event: Event) -> None:
        from aether.ui.overlay_model import CursorState
        x = event.payload.get("x", 0.5)
        y = event.payload.get("y", 0.5)
        state_str = event.payload.get("state", "default")
        state = CursorState(state_str) if state_str in CursorState.__members__.values() else CursorState.DEFAULT
        self._model.update_cursor(x, y, state)

    # ── Gesture events ──────────────────────────────────────────────

    def _on_gesture_started(self, event: Event) -> None:
        from aether.ui.overlay_model import GesturePhase
        self._model.update_gesture(
            name=event.payload.get("gesture", "Unknown"),
            phase=GesturePhase.STARTED,
            confidence=event.payload.get("confidence", 0.0),
            hand=event.payload.get("hand", "Unknown"),
        )

    def _on_gesture_holding(self, event: Event) -> None:
        from aether.ui.overlay_model import GesturePhase
        self._model.update_gesture(
            name=event.payload.get("gesture", "Unknown"),
            phase=GesturePhase.HOLDING,
            confidence=event.payload.get("confidence", 0.0),
            hand=event.payload.get("hand", "Unknown"),
        )

    def _on_gesture_ended(self, event: Event) -> None:
        self._model.clear_gesture()

    # ── Frame events ────────────────────────────────────────────────

    def _on_frame_ready(self, event: Event) -> None:
        self._frame_count += 1
        now = time.time()
        elapsed = now - self._last_fps_time
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._last_fps_time = now
            self._model.update_scene(fps=round(self._fps, 1))

    # ── Camera events ───────────────────────────────────────────────

    def _on_camera_started(self, event: Event) -> None:
        self._model.update_scene(camera_active=True)

    def _on_camera_stopped(self, event: Event) -> None:
        self._model.update_scene(camera_active=False)

    # ── Tracking events ─────────────────────────────────────────────

    def _on_tracking_lost(self, event: Event) -> None:
        self._model.update_scene(tracking=False)

    def _on_tracking_recovered(self, event: Event) -> None:
        self._model.update_scene(tracking=True)

    # ── Notification events ─────────────────────────────────────────

    def _on_notification(self, event: Event) -> None:
        text = event.payload.get("text", "")
        ttl = event.payload.get("ttl", 3.0)
        if text:
            self._model.push_notification(text, ttl)

    # ── Cursor command events ───────────────────────────────────────

    def _on_cursor_drag_start(self, event: Event) -> None:
        from aether.ui.overlay_model import CursorState
        target = event.payload.get("drag_target", "")
        self._model.update_cursor_state(CursorState.DRAG_START, drag_target=target)

    def _on_cursor_drag_end(self, event: Event) -> None:
        from aether.ui.overlay_model import CursorState
        self._model.update_cursor_state(CursorState.DRAG_END, selection_glow=True)

    def _on_cursor_draggable(self, event: Event) -> None:
        from aether.ui.overlay_model import CursorState
        self._model.update_cursor_state(CursorState.HOVER)

    def _on_cursor_idle(self, event: Event) -> None:
        from aether.ui.overlay_model import CursorState
        self._model.update_cursor_state(CursorState.DEFAULT)
