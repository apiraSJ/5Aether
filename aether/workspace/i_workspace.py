"""IWorkspace — abstract interface for workspace definitions.

Workspace describes available panels, startup behavior, and default layout.
It does NOT store geometry — that is Layout's responsibility.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IWorkspace(ABC):
    """Abstract interface for a workspace definition.

    Workspace = "what panels exist and how they behave"
    Layout    = "where panels are positioned"

    A workspace owns a layout reference but does not contain geometry.
    """

    @property
    @abstractmethod
    def workspace_id(self) -> str:
        """Unique workspace identifier (e.g. 'hand', 'vision', 'memory', 'developer')."""
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable label (e.g. 'Hand Workspace', 'Vision Workspace')."""
        ...

    @property
    @abstractmethod
    def panel_ids(self) -> List[str]:
        """List of panel IDs that belong to this workspace."""
        ...

    @property
    @abstractmethod
    def default_layout(self) -> Optional[str]:
        """Name of the default layout for this workspace, or None."""
        ...

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize workspace definition to dict."""
        ...

    @classmethod
    @abstractmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IWorkspace":
        """Deserialize workspace definition from dict."""
        ...
