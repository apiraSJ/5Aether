"""PanelSession — persistent state for a panel across widget lifecycle.

When a panel widget is destroyed (close) and reopened, the session
preserves state: search query, scroll position, chat history, etc.

Session survives widget destruction. Widget recreates from session on mount.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PanelSession:
    """Persistent state for a panel.

    Created on first mount. Survives widget destroy/recreate.
    Serialized by WorkspaceManager for layout persistence.
    """

    panel_id: str
    panel_type: str

    # Geometry (saved/restored)
    x: int = 0
    y: int = 0
    w: int = 400
    h: int = 300
    z_index: int = 10
    visible: bool = True
    docked: bool = False
    dock_edge: str = ""  # left, right, top, bottom, ""
    minimized: bool = False
    maximized: bool = False
    pinned: bool = False

    # State (panel-specific, saved/restored)
    state: dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: float = field(default_factory=time.time)
    last_focused_at: float = 0.0
    focus_count: int = 0

    def save_state(self, key: str, value: Any) -> None:
        """Save a panel-specific state value."""
        self.state[key] = value

    def load_state(self, key: str, default: Any = None) -> Any:
        """Load a panel-specific state value."""
        return self.state.get(key, default)

    def clear_state(self) -> None:
        """Clear all panel-specific state."""
        self.state.clear()

    def on_focus(self) -> None:
        """Called when panel gains focus."""
        self.last_focused_at = time.time()
        self.focus_count += 1

    def serialize(self) -> dict:
        """Serialize session for persistence."""
        return {
            "panel_id": self.panel_id,
            "panel_type": self.panel_type,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "z_index": self.z_index,
            "visible": self.visible,
            "docked": self.docked,
            "dock_edge": self.dock_edge,
            "minimized": self.minimized,
            "maximized": self.maximized,
            "pinned": self.pinned,
            "state": dict(self.state),
            "created_at": self.created_at,
            "last_focused_at": self.last_focused_at,
            "focus_count": self.focus_count,
        }

    @classmethod
    def deserialize(cls, data: dict) -> PanelSession:
        """Restore session from serialized data."""
        return cls(
            panel_id=data.get("panel_id", ""),
            panel_type=data.get("panel_type", ""),
            x=data.get("x", 0),
            y=data.get("y", 0),
            w=data.get("w", 400),
            h=data.get("h", 300),
            z_index=data.get("z_index", 10),
            visible=data.get("visible", True),
            docked=data.get("docked", False),
            dock_edge=data.get("dock_edge", ""),
            minimized=data.get("minimized", False),
            maximized=data.get("maximized", False),
            pinned=data.get("pinned", False),
            state=data.get("state", {}),
            created_at=data.get("created_at", time.time()),
            last_focused_at=data.get("last_focused_at", 0.0),
            focus_count=data.get("focus_count", 0),
        )
