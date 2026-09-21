"""IPanel — abstract interface for all Aether panels.

Design principle: interface-first, implementation-agnostic.
Qt panels (PySide6), XR panels (spatial), headless panels (CLI).
All implement IPanel.

Methods are intentionally minimal — concrete panels
extend with their own capabilities.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class IPanel(ABC):
    """Abstract interface for a UI panel.

    Lifecycle:
        create() → show() → [hide() ↔ show()] → destroy()

    Panels never modify state directly. They read from a model,
    render their content, and publish events through EventBus
    when the user interacts with them.
    """

    @abstractmethod
    def panel_id(self) -> str:
        """Unique panel identifier (e.g. 'memory', 'vision', 'system')."""
        ...

    @abstractmethod
    def show(self) -> None:
        """Make the panel visible."""
        ...

    @abstractmethod
    def hide(self) -> None:
        """Make the panel invisible."""
        ...

    @abstractmethod
    def is_visible(self) -> bool:
        """Check if the panel is currently visible."""
        ...

    @abstractmethod
    def move(self, x: int, y: int) -> None:
        """Move the panel to screen coordinates (x, y)."""
        ...

    @abstractmethod
    def resize(self, width: int, height: int) -> None:
        """Resize the panel to the given dimensions."""
        ...

    @abstractmethod
    def geometry(self) -> tuple[int, int, int, int]:
        """Return (x, y, width, height)."""
        ...

    @abstractmethod
    def set_geometry(self, x: int, y: int, width: int, height: int) -> None:
        """Set position and size in one call."""
        ...

    @abstractmethod
    def set_theme(self, theme: dict) -> None:
        """Apply a theme dict to this panel.

        Theme dict contains:
            colors: {background, primary, warning, error}
            opacity: {panel, overlay}
            typography: {font, title_size, body_size}
            shape: {border_radius}
            animation: {duration_ms}
        """
        ...

    @abstractmethod
    def set_z_index(self, z_index: int) -> None:
        """Set the panel's z-index within its layer."""
        ...

    @abstractmethod
    def get_z_index(self) -> int:
        """Get the panel's z-index."""
        ...

    @abstractmethod
    def focus(self) -> None:
        """Bring the panel to focus (top of z-order, input priority)."""
        ...

    @abstractmethod
    def has_focus(self) -> bool:
        """Check if the panel currently has focus."""
        ...

    @abstractmethod
    def update(self) -> None:
        """Update panel state from its data source. Called by HUDManager."""
        ...

    @abstractmethod
    def paint(self) -> None:
        """Render the panel. Called by HUDManager after update()."""
        ...
