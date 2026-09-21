"""ILayout — abstract interface for layout definitions.

Layout stores only geometry, z-order, docking, floating, and visibility state.
It does NOT describe what panels exist — that is Workspace's responsibility.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ILayout(ABC):
    """Abstract interface for a layout.

    Layout = "where panels are"
    Workspace = "what panels exist"

    A layout is owned by a workspace but stored separately.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Layout name (e.g. 'hand_default', 'vision_debug')."""
        ...

    @property
    @abstractmethod
    def workspace_id(self) -> Optional[str]:
        """Workspace this layout belongs to, or None if universal."""
        ...

    @property
    @abstractmethod
    def panel_geometries(self) -> Dict[str, Dict[str, Any]]:
        """Panel geometries keyed by panel id.

        Each entry: {x, y, w, h, z_index, dock, visible}
        """
        ...

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize layout to dict."""
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ILayout":
        """Deserialize layout from dict."""
        ...
