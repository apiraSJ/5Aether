"""NotificationManager — notification aggregator service.

Flow:
    Service/Plugin -> notify()/publish() -> NotificationManager
    EventBus event  -> _on_event()       -> NotificationManager (translation)

NotificationManager is an Event Aggregator:
    - subscribes to EventBus events, translates them into Notifications
    - filters, dedupes, and keeps a ring buffer (deque maxlen=100)
    - publishes NOTIFICATION_CREATED (+ legacy NOTIFICATION_SHOW) so the
      widget subscribes to exactly one event type and never touches internals

Levels:
    info:    3 seconds auto-dismiss
    success: 3 seconds auto-dismiss
    warning: 5 seconds auto-dismiss
    error:   manual dismiss only (duration=0)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("Aether.NotificationManager")


class Notification:
    """A single notification."""

    __slots__ = ("id", "text", "type", "duration", "created_at", "dismissed", "action")

    def __init__(self, text: str, ntype: str = "info", duration: float = 0.0,
                 action: Optional[Dict[str, Any]] = None) -> None:
        self.id: int = id(self)
        self.text = text
        self.type = ntype
        self.duration = duration if duration > 0 else self._default_duration(ntype)
        self.created_at = time.time()
        self.dismissed = False
        self.action = action

    def _default_duration(self, ntype: str) -> float:
        return {"info": 3.0, "success": 3.0, "warning": 5.0, "error": 0.0}.get(ntype, 3.0)

    @property
    def expired(self) -> bool:
        if self.duration <= 0:
            return False  # manual dismiss only
        return (time.time() - self.created_at) >= self.duration

    @property
    def elapsed(self) -> float:
        return time.time() - self.created_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "type": self.type,
            "level": self.type,
            "duration": self.duration,
            "elapsed": round(self.elapsed, 1),
            "expired": self.expired,
            "created_at": self.created_at,
            "action": self.action,
        }


def _default_text(event_type, payload: dict) -> str:
    """Best-effort human text for a translated event payload."""
    return payload.get("message") or payload.get("title") or str(event_type)


class NotificationManager:
    """Aggregates EventBus events into notifications and manages lifecycle.

    Also keeps a direct notify()/publish() API for non-event sources.
    """

    RING_BUFFER_SIZE = 100
    DEDUPE_WINDOW_SECONDS = 5.0

    def __init__(self, event_bus: Any = None) -> None:
        self._event_bus = event_bus
        self._notifications: deque[Notification] = deque(maxlen=self.RING_BUFFER_SIZE)
        self._lock = threading.RLock()
        self._max_notifications = 50
        self._last_similar: Dict[str, float] = {}

        self._subscribed = False
        if event_bus is not None and hasattr(event_bus, "subscribe"):
            self.subscribe_events()

    # ── Event translation map ───────────────────────────────────────

    def _translation_map(self) -> Dict[Any, Callable[[dict], dict]]:
        """EventType -> payload extractor returning {text, type, action}."""
        return {
            "memory.created": lambda p: {
                "text": f"Memory saved: {(p.get('record') or {}).get('title') or _default_text('memory.created', p)}",
                "type": "success",
                "action": {"command": "ui.panel.focus", "params": {"panel_id": "memory"}},
            },
            "memory.updated": lambda p: {
                "text": f"Memory updated: {_default_text('memory.updated', p)}",
                "type": "info",
            },
            "memory.pinned": lambda p: {
                "text": "Memory pinned",
                "type": "success",
                "action": {"command": "ui.panel.focus", "params": {"panel_id": "memory"}},
            },
            "memory.unpinned": lambda p: {
                "text": "Memory unpinned",
                "type": "info",
                "action": {"command": "ui.panel.focus", "params": {"panel_id": "memory"}},
            },
            "layout.saved": lambda p: {
                "text": f"Layout saved: {p.get('name', 'unknown')}",
                "type": "success",
            },
            "layout.loaded": lambda p: {
                "text": f"Layout loaded: {p.get('name', 'unknown')}",
                "type": "info",
            },
            "workspace.loaded": lambda p: {
                "text": f"Workspace loaded: {p.get('name', '')}",
                "type": "info",
            },
            "task.completed": lambda p: {
                "text": f"Task completed: {p.get('title', _default_text('task.completed', p))}",
                "type": "success",
                "action": {"command": "ui.panel.focus", "params": {"panel_id": "tasks"}},
            },
            "plugin.error": lambda p: {
                "text": f"Plugin error: {_default_text('plugin.error', p)}",
                "type": "error",
            },
            "system.error": lambda p: {
                "text": f"System error: {_default_text('system.error', p)}",
                "type": "error",
            },
            "command.failed": lambda p: {
                "text": f"Command failed: {p.get('command', 'unknown')}",
                "type": "error",
            },
            "vision.tracking.lost": lambda p: {
                "text": "Vision tracking lost",
                "type": "warning",
            },
            "vision.tracking.recovered": lambda p: {
                "text": "Vision tracking recovered",
                "type": "success",
            },
        }

    def subscribe_events(self) -> bool:
        """Subscribe the aggregator to the translation map on the EventBus."""
        if self._subscribed:
            return True
        if self._event_bus is None or not hasattr(self._event_bus, "subscribe"):
            return False
        for event_type in self._translation_map():
            try:
                self._event_bus.subscribe(event_type, self._on_event)
            except Exception:
                logger.exception("Failed to subscribe to %s", event_type)
        self._subscribed = True
        logger.info("NotificationManager subscribed to %d event types",
                    len(self._translation_map()))
        return True

    def unsubscribe(self) -> None:
        if not self._subscribed or self._event_bus is None:
            return
        for event_type in self._translation_map():
            try:
                self._event_bus.unsubscribe(event_type, self._on_event)
            except Exception:
                pass
        self._subscribed = False

    def _on_event(self, event) -> None:
        """Translate an EventBus event into a notification."""
        from aether.core.event_type import EventType
        if isinstance(event.type, EventType):
            event_name = event.type.value
        else:
            event_name = str(event.type)
        extract = self._translation_map().get(event_name)
        if extract is None:
            return
        payload = event.payload if isinstance(event.payload, dict) else {}
        try:
            spec = extract(payload)
        except Exception:
            logger.exception("Notification translation failed for %s", event.type)
            return
        self.notify(
            spec.get("text", "Notification"),
            level=spec.get("type", "info"),
            action=spec.get("action"),
        )

    # ── Publish ─────────────────────────────────────────────────────

    def notify(self, text: str, level: str = "info",
               duration: float = 0.0,
               action: Optional[Dict[str, Any]] = None) -> Notification:
        """Create and publish a notification (level names: info/success/warning/error)."""
        return self.publish(text, level, duration, action=action)

    def publish(self, text: str, ntype: str = "info", duration: float = 0.0,
                action: Optional[Dict[str, Any]] = None) -> Notification:
        """Publish a notification. Returns the Notification object."""
        if self._is_duplicate(text):
            return self._last_notification(text)
        notif = Notification(text, ntype, duration, action=action)
        with self._lock:
            self._notifications.append(notif)
            self._last_similar[text] = notif.created_at
            # Trim old dismissed/expired
            self._trim()
        self._emit_created(notif)
        self._emit_event(notif)
        logger.info("Notification [%s]: %s", ntype, text)
        return notif

    def info(self, text: str) -> Notification:
        return self.publish(text, "info")

    def success(self, text: str) -> Notification:
        return self.publish(text, "success")

    def warning(self, text: str) -> Notification:
        return self.publish(text, "warning")

    def error(self, text: str) -> Notification:
        return self.publish(text, "error")

    # ── Dismiss ────────────────────────────────────────────────────

    def dismiss(self, notification_id: int) -> bool:
        """Dismiss a notification by id. Returns True if found."""
        with self._lock:
            for n in self._notifications:
                if n.id == notification_id and not n.dismissed:
                    n.dismissed = True
                    self._emit_dismiss(n)
                    return True
        return False

    def clear(self) -> int:
        """Clear all notifications. Returns count cleared."""
        with self._lock:
            count = len(self._notifications)
            self._notifications.clear()
        logger.info("Cleared %d notifications", count)
        return count

    # ── Query ──────────────────────────────────────────────────────

    def get_active(self) -> List[Notification]:
        """Return non-expired, non-dismissed notifications."""
        with self._lock:
            return [
                n for n in self._notifications
                if not n.dismissed and not n.expired
            ]

    def get_all(self) -> List[Notification]:
        """Return all notifications (including expired/dismissed)."""
        with self._lock:
            return list(self._notifications)

    def count(self) -> int:
        """Count of active notifications."""
        return len(self.get_active())

    # ── Expire ─────────────────────────────────────────────────────

    def expire_stale(self) -> int:
        """Expire old notifications. Returns count expired."""
        expired = 0
        with self._lock:
            for n in self._notifications:
                if not n.dismissed and n.expired:
                    n.dismissed = True
                    expired += 1
        return expired

    # ── Dedupe ─────────────────────────────────────────────────────

    def _is_duplicate(self, text: str) -> bool:
        now = time.time()
        last = self._last_similar.get(text)
        if last is not None and (now - last) < self.DEDUPE_WINDOW_SECONDS:
            return True
        return False

    def _last_notification(self, text: str) -> Optional[Notification]:
        with self._lock:
            for n in reversed(self._notifications):
                if n.text == text:
                    return n
        return None

    # ── Internal ───────────────────────────────────────────────────

    def _emit_created(self, notif: Notification) -> None:
        """Publish NOTIFICATION_CREATED event (the one the widget subscribes to)."""
        if not self._event_bus:
            return
        try:
            from aether.core.event_bus_v2 import Event
            from aether.core.event_type import EventType
            self._event_bus.publish(Event(
                type=EventType.NOTIFICATION_CREATED,
                payload=notif.to_dict(),
                source="notification_manager",
            ))
        except Exception:
            logger.exception("Failed to publish notification.created event")

    def _emit_event(self, notif: Notification) -> None:
        """Publish legacy NOTIFICATION_SHOW event through EventBus."""
        if not self._event_bus:
            return
        try:
            from aether.core.event_bus_v2 import Event
            from aether.core.event_type import EventType
            self._event_bus.publish(Event(
                type=EventType.NOTIFICATION_SHOW,
                payload=notif.to_dict(),
                source="notification_manager",
            ))
        except Exception:
            logger.exception("Failed to publish notification event")

    def _emit_dismiss(self, notif: Notification) -> None:
        """Publish NOTIFICATION_DISMISS event through EventBus."""
        if not self._event_bus:
            return
        try:
            from aether.core.event_bus_v2 import Event
            from aether.core.event_type import EventType
            self._event_bus.publish(Event(
                type=EventType.NOTIFICATION_DISMISS,
                payload=notif.to_dict(),
                source="notification_manager",
            ))
        except Exception:
            logger.exception("Failed to publish dismiss event")

    def _trim(self) -> None:
        """Remove oldest dismissed/expired if over limit."""
        if len(self._notifications) <= self._max_notifications:
            return
        active = [n for n in self._notifications if not (n.dismissed or n.expired)]
        keep = len(active)
        kept = []
        for n in self._notifications:
            if n.dismissed or n.expired:
                if keep >= self._max_notifications:
                    continue
                keep += 1
            kept.append(n)
        self._notifications = deque(kept, maxlen=self.RING_BUFFER_SIZE)
