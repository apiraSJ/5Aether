"""PanelInfo — metadata for a registered panel.

Stored in PanelRegistry. Useful for AI introspection:
'what panels exist?', 'which panels support move?'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


class PanelCapability(Enum):
    """Capabilities a panel may support."""

    MOVE = auto()
    RESIZE = auto()
    HIDE = auto()
    FOCUS = auto()
    DRAG = auto()
    MINIMIZE = auto()
    MAXIMIZE = auto()


@dataclass
class PanelInfo:
    """Metadata about a registered panel.

    Attributes:
        id:           Unique panel identifier.
        type:         Panel category (e.g. 'memory', 'vision', 'system').
        label:        Human-readable name for display.
        description:  One-line description for AI / help.
        capabilities: What the panel supports.
        z_index:      Z-ordering within its layer.
        visible:      Current visibility state.
        x, y, w, h:  Default geometry.
        has_focus:    Whether this panel currently has focus.
        widget:       The actual panel widget (IPanel implementation).
        tags:         Freeform tags for filtering (e.g. ['spatial', 'data']).
    """

    id: str
    type: str
    label: str = ""
    description: str = ""
    capabilities: List[PanelCapability] = field(
        default_factory=lambda: [
            PanelCapability.MOVE,
            PanelCapability.RESIZE,
            PanelCapability.HIDE,
            PanelCapability.FOCUS,
        ]
    )
    z_index: int = 0
    visible: bool = False
    x: int = 0
    y: int = 0
    w: int = 400
    h: int = 300
    has_focus: bool = False
    widget: Optional[object] = None
    tags: List[str] = field(default_factory=list)

    def has_capability(self, cap: PanelCapability) -> bool:
        return cap in self.capabilities

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict (excludes widget reference)."""
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "description": self.description,
            "capabilities": [c.name for c in self.capabilities],
            "z_index": self.z_index,
            "visible": self.visible,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "has_focus": self.has_focus,
            "tags": self.tags,
        }
