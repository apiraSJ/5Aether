"""IInteractionTarget — abstract interface for any draggable/resizable/selectable target.

Allows InteractionController to work with any target type:
- Panels (Sprint 1)
- Memory cards (Future)
- Object nodes (Future)
- Timeline items (Future)
- Desktop windows (Future)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple


class IInteractionTarget(ABC):
    """Abstract interface for an interaction target.

    InteractionController operates on IInteractionTarget instances,
    not on panels directly. This allows the same state machine to
    handle drag/resize/select for any UI element.
    """

    @property
    @abstractmethod
    def target_id(self) -> str:
        """Unique target identifier."""
        ...

    @property
    @abstractmethod
    def target_type(self) -> str:
        """Target type discriminator (e.g. 'panel', 'memory_card', 'node')."""
        ...

    @abstractmethod
    def get_geometry(self) -> Tuple[float, float, float, float]:
        """Return (x, y, width, height)."""
        ...

    @abstractmethod
    def set_position(self, x: float, y: float) -> None:
        """Move target to screen coordinates (x, y)."""
        ...

    @abstractmethod
    def set_size(self, width: float, height: float) -> None:
        """Resize target to given dimensions."""
        ...

    @abstractmethod
    def set_geometry(self, x: float, y: float, width: float, height: float) -> None:
        """Set position and size in one call."""
        ...

    @abstractmethod
    def hit_test(self, x: float, y: float) -> Optional[str]:
        """Test if (x, y) is within this target.

        Returns 'body', 'edge_top', 'edge_bottom', 'edge_left', 'edge_right',
        'corner_tl', 'corner_tr', 'corner_bl', 'corner_br', or None.
        """
        ...

    @abstractmethod
    def get_z_index(self) -> int:
        """Get the target's z-index."""
        ...

    @abstractmethod
    def set_z_index(self, z_index: int) -> None:
        """Set the target's z-index."""
        ...
