"""IPanelWidget — interface for all workspace panel widgets.

Composition: a PanelWidget is a QWidget that wraps a panel model
(AbstractPanel subclass). Geometry, visibility, and focus are synced
by PanelRegistry — widgets never decide layout themselves.

Lifecycle (similar to React mounting):
    created → mount() → show() → [hide() ↔ show()] → unmount() → destroy()
                ↓
            focused → blurred

Events emitted through EventBus:
    panel.mounted, panel.unmounted, panel.focused, panel.blurred,
    panel.shown, panel.hidden, panel.destroyed
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Optional


class IPanelWidget:
    """Interface for a panel widget hosted in the Workspace layer.

    Every panel widget (Memory, AI Chat, Tasks, Dashboard, Camera)
    implements this interface so the WidgetFactory and PanelRegistry
    can manage them uniformly.
    """

    @property
    @abstractmethod
    def panel_id(self) -> str:
        """Unique identifier matching PanelInfo.id."""
        ...

    @property
    @abstractmethod
    def panel_type(self) -> str:
        """Panel category matching PanelInfo.type (e.g. 'memory', 'ai_chat')."""
        ...

    # ── Lifecycle ───────────────────────────────────────────────────

    @abstractmethod
    def mount(self) -> None:
        """Called when widget is added to the HUD Workspace layer."""
        ...

    @abstractmethod
    def unmount(self) -> None:
        """Called when widget is removed from the HUD Workspace layer."""
        ...

    @abstractmethod
    def destroy(self) -> None:
        """Called when widget is being destroyed (cleanup resources)."""
        ...

    # ── Focus ───────────────────────────────────────────────────────

    @abstractmethod
    def focus_widget(self) -> None:
        """Called by PanelRegistry when this panel gains focus.

        Should raise widget to top, apply focus styling.
        """
        ...

    @abstractmethod
    def blur_widget(self) -> None:
        """Called by PanelRegistry when this panel loses focus.

        Should remove focus styling.
        """
        ...

    @abstractmethod
    def has_focus(self) -> bool:
        """Whether this widget currently has focus."""
        ...

    # ── Geometry ────────────────────────────────────────────────────

    @abstractmethod
    def set_geometry(self, x: int, y: int, w: int, h: int) -> None:
        """Set position and size. Called by PanelRegistry."""
        ...

    @abstractmethod
    def geometry(self) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) for serialization."""
        ...

    # ── Data ────────────────────────────────────────────────────────

    @abstractmethod
    def update_content(self) -> None:
        """Refresh panel from its data model. Called per frame by HUDManager."""
        ...

    # ── Serialization ───────────────────────────────────────────────

    @abstractmethod
    def serialize(self) -> dict:
        """Serialize panel state (e.g. search query, scroll position)."""
        ...

    @abstractmethod
    def restore(self, state: dict) -> None:
        """Restore panel state from serialized data."""
        ...
