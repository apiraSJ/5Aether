"""SelectionManager — tracks which panel is selected for interaction.

Selection is different from focus:
- Focus = which panel receives keyboard input
- Selection = which panel is being interacted with (drag, resize)

A panel can be focused without being selected, and vice versa.
"""

from __future__ import annotations

import logging
from typing import Optional

from aether.ui.panel.panel_registry import PanelRegistry

logger = logging.getLogger("Aether.SelectionManager")


class SelectionManager:
    """Manages panel selection state.

    Selected panel:
        - Highlighted visually
        - Can be dragged
        - Can be resized
        - Receives click events
    """

    def __init__(self, panel_registry: PanelRegistry) -> None:
        self._registry = panel_registry
        self._selected_id: Optional[str] = None

    @property
    def selected_panel_id(self) -> Optional[str]:
        return self._selected_id

    @property
    def has_selection(self) -> bool:
        return self._selected_id is not None

    def select(self, panel_id: str) -> bool:
        """Select a panel. Returns True if panel found and selected."""
        # Deselect current
        self._deselect_current()

        info = self._registry.get(panel_id)
        if not info:
            return False

        self._selected_id = panel_id
        logger.debug("Selected: '%s'", panel_id)
        return True

    def deselect(self) -> None:
        """Deselect the current panel."""
        self._deselect_current()

    def _deselect_current(self) -> None:
        if self._selected_id:
            logger.debug("Deselected: '%s'", self._selected_id)
            self._selected_id = None

    def is_selected(self, panel_id: str) -> bool:
        return self._selected_id == panel_id

    def get_selected_info(self):
        """Get PanelInfo for the selected panel."""
        if self._selected_id:
            return self._registry.get(self._selected_id)
        return None
