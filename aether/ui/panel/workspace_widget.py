"""WorkspaceWidget — transparent container for workspace PanelWidgets.

Added to HUD layer 2 (Workspace). PanelWidgets are children of this
widget, positioned absolutely by WorkspaceManager via PanelRegistry.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from aether.ui.panel.panel_widget import PanelWidget


class WorkspaceWidget(QWidget):
    """Container that hosts all workspace panel widgets.

    Each PanelWidget is a child positioned absolutely within this
    container. The container itself is transparent and fills the
    entire HUD area.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground)
        self._panels: dict[str, PanelWidget] = {}

    def add_panel(self, widget: PanelWidget) -> None:
        """Add a panel widget as a child of this container."""
        self._panels[widget.panel_id] = widget
        widget.setParent(self)
        widget.setVisible(True)
        widget.mount()

    def remove_panel(self, panel_id: str) -> Optional[PanelWidget]:
        """Remove and return a panel widget."""
        widget = self._panels.pop(panel_id, None)
        if widget:
            widget.unmount()
            widget.setParent(None)
        return widget

    def get_panel(self, panel_id: str) -> Optional[PanelWidget]:
        return self._panels.get(panel_id)

    def clear(self) -> None:
        for pid in list(self._panels):
            self.remove_panel(pid)

    @property
    def panel_count(self) -> int:
        return len(self._panels)
