"""FocusManager — tracks which panel has input focus.

Focus determines which panel receives keyboard input and is
brought to the front of z-order when clicked.
"""

from __future__ import annotations

import logging
from typing import Optional

from aether.ui.panel.panel_registry import PanelRegistry

logger = logging.getLogger("Aether.FocusManager")


class FocusManager:
    """Manages panel focus state.

    When a panel receives focus:
        - It gets brought to front z-index
        - Previous focused panel loses focus
        - PANEL_FOCUSED event is emitted
    """

    def __init__(self, panel_registry: PanelRegistry) -> None:
        self._registry = panel_registry
        self._focused_id: Optional[str] = None

    @property
    def focused_panel_id(self) -> Optional[str]:
        return self._focused_id

    @property
    def has_focus(self) -> bool:
        return self._focused_id is not None

    def focus(self, panel_id: str) -> bool:
        """Give focus to a panel. Returns True if panel found and focused."""
        # Unfocus current
        if self._focused_id and self._focused_id != panel_id:
            old_info = self._registry.get(self._focused_id)
            if old_info:
                old_info.has_focus = False

        # Focus new panel
        info = self._registry.get(panel_id)
        if not info:
            return False

        info.has_focus = True
        self._focused_id = panel_id

        # Bring to front
        self._registry.focus_panel(panel_id)

        logger.debug("Focus: '%s'", panel_id)
        return True

    def unfocus(self) -> None:
        """Remove focus from all panels."""
        if self._focused_id:
            info = self._registry.get(self._focused_id)
            if info:
                info.has_focus = False
            logger.debug("Unfocus: '%s'", self._focused_id)
            self._focused_id = None

    def is_focused(self, panel_id: str) -> bool:
        return self._focused_id == panel_id
