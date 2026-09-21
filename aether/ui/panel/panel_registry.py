"""PanelRegistry — central registry for all Aether panels.

Stores PanelInfo for each panel. Panels are explicitly registered,
not auto-discovered. AI and CLI can query 'what panels exist?'.

Implements IService for DI container registration.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, List, Optional

from aether.ui.panel.panel_info import PanelInfo, PanelCapability

logger = logging.getLogger("Aether.PanelRegistry")


class PanelRegistry:
    """Thread-safe registry of panels.

    Usage:
        registry = PanelRegistry()
        registry.register(PanelInfo(id="memory", type="memory", ...))
        registry.show_panel("memory")

    Optionally accepts an EventBus to emit panel lifecycle events:
        PANEL_SHOWN, PANEL_HIDDEN, PANEL_MOVED, PANEL_FOCUSED, PANEL_REGISTERED
    """

    def __init__(self, event_bus: Optional[object] = None) -> None:
        self._panels: Dict[str, PanelInfo] = {}
        self._lock = threading.RLock()
        self._on_change: Optional[Callable[[str, str], None]] = None
        self._event_bus = event_bus

    def set_change_listener(self, callback: Callable[[str, str], None]) -> None:
        """Set a listener called on (panel_id, action) for state changes."""
        self._on_change = callback

    def register(self, info: PanelInfo) -> None:
        """Register a panel. Overwrites if id already exists."""
        with self._lock:
            self._panels[info.id] = info
        logger.info("Panel registered: '%s' (type=%s, z=%d)", info.id, info.type, info.z_index)
        self._notify(info.id, "registered")

    def unregister(self, panel_id: str) -> bool:
        """Remove a panel. Returns True if found and removed."""
        with self._lock:
            removed = self._panels.pop(panel_id, None)
        if removed:
            logger.info("Panel unregistered: '%s'", panel_id)
            self._notify(panel_id, "unregistered")
        return removed is not None

    def get(self, panel_id: str) -> Optional[PanelInfo]:
        """Get panel info by id."""
        with self._lock:
            return self._panels.get(panel_id)

    def get_widget(self, panel_id: str) -> Optional[object]:
        """Get the widget instance for a panel."""
        with self._lock:
            info = self._panels.get(panel_id)
            return info.widget if info else None

    def list_all(self) -> List[PanelInfo]:
        """Return all registered panels."""
        with self._lock:
            return list(self._panels.values())

    def list_visible(self) -> List[PanelInfo]:
        """Return only visible panels."""
        with self._lock:
            return [p for p in self._panels.values() if p.visible]

    def list_by_type(self, panel_type: str) -> List[PanelInfo]:
        """Return panels matching a type."""
        with self._lock:
            return [p for p in self._panels.values() if p.type == panel_type]

    def list_with_capability(self, cap: PanelCapability) -> List[PanelInfo]:
        """Return panels that have a specific capability."""
        with self._lock:
            return [p for p in self._panels.values() if p.has_capability(cap)]

    def panel_count(self) -> int:
        """Total registered panels."""
        with self._lock:
            return len(self._panels)

    # ── Visibility ─────────────────────────────────────────────────

    def show_panel(self, panel_id: str) -> bool:
        """Show a panel. Returns True if found."""
        with self._lock:
            info = self._panels.get(panel_id)
            if not info:
                return False
            info.visible = True
            if info.widget and hasattr(info.widget, "show"):
                info.widget.show()
        self._notify(panel_id, "shown")
        return True

    def hide_panel(self, panel_id: str) -> bool:
        """Hide a panel. Returns True if found."""
        with self._lock:
            info = self._panels.get(panel_id)
            if not info:
                return False
            info.visible = False
            info.has_focus = False
            if info.widget and hasattr(info.widget, "hide"):
                info.widget.hide()
        self._notify(panel_id, "hidden")
        return True

    def toggle_panel(self, panel_id: str) -> bool:
        """Toggle visibility. Returns new visibility state."""
        with self._lock:
            info = self._panels.get(panel_id)
            if not info:
                return False
            info.visible = not info.visible
            if info.widget:
                if info.visible and hasattr(info.widget, "show"):
                    info.widget.show()
                elif not info.visible and hasattr(info.widget, "hide"):
                    info.widget.hide()
        action = "shown" if info.visible else "hidden"
        self._notify(panel_id, action)
        return info.visible

    # ── Geometry ───────────────────────────────────────────────────

    def move_panel(self, panel_id: str, x: int, y: int) -> bool:
        """Move a panel. Returns True if found."""
        with self._lock:
            info = self._panels.get(panel_id)
            if not info:
                return False
            info.x = x
            info.y = y
            if info.widget and hasattr(info.widget, "move"):
                info.widget.move(x, y)
        self._notify(panel_id, "moved")
        return True

    def resize_panel(self, panel_id: str, width: int, height: int) -> bool:
        """Resize a panel. Returns True if found."""
        with self._lock:
            info = self._panels.get(panel_id)
            if not info:
                return False
            info.w = width
            info.h = height
            if info.widget and hasattr(info.widget, "resize"):
                info.widget.resize(width, height)
        self._notify(panel_id, "resized")
        return True

    def set_geometry(self, panel_id: str, x: int, y: int, w: int, h: int) -> bool:
        """Set position and size. Returns True if found."""
        with self._lock:
            info = self._panels.get(panel_id)
            if not info:
                return False
            info.x, info.y, info.w, info.h = x, y, w, h
            if info.widget and hasattr(info.widget, "set_geometry"):
                info.widget.set_geometry(x, y, w, h)
        self._notify(panel_id, "geometry_changed")
        return True

    # ── Z-Index ────────────────────────────────────────────────────

    def set_z_index(self, panel_id: str, z_index: int) -> bool:
        """Set panel z-index. Returns True if found."""
        with self._lock:
            info = self._panels.get(panel_id)
            if not info:
                return False
            info.z_index = z_index
            if info.widget and hasattr(info.widget, "set_z_index"):
                info.widget.set_z_index(z_index)
        return True

    def get_sorted_by_z(self) -> List[PanelInfo]:
        """Return panels sorted by z-index (lowest first)."""
        with self._lock:
            return sorted(self._panels.values(), key=lambda p: p.z_index)

    # ── Focus ──────────────────────────────────────────────────────

    def focus_panel(self, panel_id: str) -> bool:
        """Give focus to a panel, removing focus from others. Returns True if found."""
        with self._lock:
            info = self._panels.get(panel_id)
            if not info:
                return False
            for p in self._panels.values():
                p.has_focus = False
                if p.widget and hasattr(p.widget, "has_focus"):
                    pass  # widget focus state managed by panel itself
            info.has_focus = True
            if info.widget and hasattr(info.widget, "focus"):
                info.widget.focus()
        self._notify(panel_id, "focused")
        return True

    def get_focused(self) -> Optional[PanelInfo]:
        """Return the currently focused panel."""
        with self._lock:
            for p in self._panels.values():
                if p.has_focus:
                    return p
            return None

    # ── Theme ──────────────────────────────────────────────────────

    def apply_theme(self, theme: dict) -> int:
        """Apply a theme to all panels. Returns count of panels themed."""
        count = 0
        with self._lock:
            for info in self._panels.values():
                if info.widget and hasattr(info.widget, "set_theme"):
                    info.widget.set_theme(theme)
                    count += 1
        return count

    # ── Serialization ──────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize all panels to a dict (for status/help)."""
        with self._lock:
            return {
                "panel_count": len(self._panels),
                "panels": [p.to_dict() for p in self._panels.values()],
            }

    # ── Internal ───────────────────────────────────────────────────

    def _notify(self, panel_id: str, action: str) -> None:
        if self._on_change:
            try:
                self._on_change(panel_id, action)
            except Exception:
                logger.exception("Panel change listener failed")
        self._emit_panel_event(panel_id, action)

    def _emit_panel_event(self, panel_id: str, action: str) -> None:
        """Emit a panel lifecycle event through EventBus if available."""
        if not self._event_bus:
            return
        try:
            from aether.core.event_bus_v2 import Event
            from aether.core.event_type import EventType

            _ACTION_MAP = {
                "registered": EventType.PANEL_REGISTERED,
                "shown": EventType.PANEL_SHOWN,
                "hidden": EventType.PANEL_HIDDEN,
                "moved": EventType.PANEL_MOVED,
                "focused": EventType.PANEL_FOCUSED,
            }
            event_type = _ACTION_MAP.get(action)
            if event_type is None:
                return

            info = self._panels.get(panel_id)
            payload = {"panel_id": panel_id}
            if info:
                payload["type"] = info.type
                payload["visible"] = info.visible
                payload["x"] = info.x
                payload["y"] = info.y

            self._event_bus.publish(Event(
                type=event_type,
                payload=payload,
                source="panel_registry",
            ))
        except Exception:
            logger.exception("Failed to emit panel event")
