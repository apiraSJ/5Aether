"""PlaceholderPanel — lightweight "Coming Soon" panel for workspaces.

Can be opened, dragged, resized, focused, docked, and saved in layouts.
Renders a simple "Coming Soon" label — no business logic.

View-only pattern:
    - Dispatches commands through CommandBus
    - Subscribes to events through EventBus
    - Never accesses services directly
"""

from __future__ import annotations

from typing import Optional

from aether.ui.panel.abstract_panel import AbstractPanel
from aether.ui.panel.panel_info import PanelCapability


class PlaceholderPanel(AbstractPanel):
    """Placeholder panel that shows "Coming Soon" content.

    Supports full interaction lifecycle (open, drag, resize, focus, dock)
    but displays placeholder content. Intended for workspaces where not
    all panels are fully implemented yet.
    """

    def __init__(
        self,
        panel_id: str,
        label: str = "Coming Soon",
        x: int = 0,
        y: int = 0,
        width: int = 400,
        height: int = 300,
        z_index: int = 10,
    ) -> None:
        super().__init__(
            panel_id=panel_id,
            x=x,
            y=y,
            width=width,
            height=height,
            z_index=z_index,
        )
        self._label = label
        self._capabilities = [
            PanelCapability.MOVE,
            PanelCapability.RESIZE,
            PanelCapability.HIDE,
            PanelCapability.FOCUS,
        ]

    @property
    def label(self) -> str:
        return self._label

    def update(self) -> None:
        pass

    def paint(self) -> None:
        pass
