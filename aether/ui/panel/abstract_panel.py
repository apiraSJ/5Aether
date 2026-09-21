"""AbstractPanel — default implementation of IPanel.

Provides sensible defaults so concrete panels (MemoryPanel, VisionPanel, etc.)
only need to override update() and paint().
"""

from __future__ import annotations

import logging
from typing import Optional

from aether.ui.panel.i_panel import IPanel
from aether.ui.panel.panel_info import PanelCapability

logger = logging.getLogger("Aether.Panel")


class AbstractPanel(IPanel):
    """Base class for all concrete panels.

    Provides:
        - geometry storage
        - visibility state
        - z-index management
        - focus tracking
        - default theme dict
        - capability checking
    """

    def __init__(
        self,
        panel_id: str,
        x: int = 0,
        y: int = 0,
        width: int = 400,
        height: int = 300,
        z_index: int = 0,
    ) -> None:
        self._panel_id = panel_id
        self._x = x
        self._y = y
        self._w = width
        self._h = height
        self._visible = False
        self._z_index = z_index
        self._has_focus = False
        self._theme: dict = {}
        self._capabilities = [
            PanelCapability.MOVE,
            PanelCapability.RESIZE,
            PanelCapability.HIDE,
            PanelCapability.FOCUS,
        ]

    def panel_id(self) -> str:
        return self._panel_id

    def show(self) -> None:
        self._visible = True
        logger.debug("Panel '%s' shown", self._panel_id)

    def hide(self) -> None:
        self._visible = False
        self._has_focus = False
        logger.debug("Panel '%s' hidden", self._panel_id)

    def is_visible(self) -> bool:
        return self._visible

    def move(self, x: int, y: int) -> None:
        self._x = x
        self._y = y

    def resize(self, width: int, height: int) -> None:
        self._w = max(1, width)
        self._h = max(1, height)

    def geometry(self) -> tuple[int, int, int, int]:
        return (self._x, self._y, self._w, self._h)

    def set_geometry(self, x: int, y: int, width: int, height: int) -> None:
        self._x = x
        self._y = y
        self._w = max(1, width)
        self._h = max(1, height)

    def set_theme(self, theme: dict) -> None:
        self._theme = theme

    def set_z_index(self, z_index: int) -> None:
        self._z_index = z_index

    def get_z_index(self) -> int:
        return self._z_index

    def focus(self) -> None:
        self._has_focus = True

    def has_focus(self) -> bool:
        return self._has_focus

    def has_capability(self, cap: PanelCapability) -> bool:
        return cap in self._capabilities

    def update(self) -> None:
        """Override in subclass to update from data source."""
        pass

    def paint(self) -> None:
        """Override in subclass to render panel."""
        pass
