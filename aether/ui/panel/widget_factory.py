"""WidgetFactory — creates PanelWidget instances per panel type.

Usage:
    factory = WidgetFactory()
    widget = factory.create_widget(panel_info)
    # Returns PanelWidget (or None if type unknown)
"""

from __future__ import annotations

import logging
from typing import Optional

from aether.ui.panel.panel_info import PanelInfo
from aether.ui.panel.panel_widget import PanelWidget
from aether.ui.panel.memory_widget import MemoryPanelWidget
from aether.ui.panel.ai_chat_widget import AIChatPanelWidget
from aether.ui.panel.tasks_widget import TasksPanelWidget
from aether.ui.panel.dashboard_widget import DashboardPanelWidget

logger = logging.getLogger("Aether.WidgetFactory")

# Map of panel type → widget class
_WIDGET_MAP: dict[str, type[PanelWidget]] = {
    "memory": MemoryPanelWidget,
    "ai_chat": AIChatPanelWidget,
    "tasks": TasksPanelWidget,
    "dashboard": DashboardPanelWidget,
    "camera": None,  # CameraWidget created separately (uses FrameBroker)
}


class WidgetFactory:
    """Creates PanelWidget instances for registered panels.

    The factory reads PanelInfo.type and instantiates the matching
    widget class. Unknown types log a warning and return None.
    """

    def create_widget(self, info: PanelInfo, parent=None) -> Optional[PanelWidget]:
        """Create a PanelWidget for the given PanelInfo.

        Returns None if the panel type has no widget implementation
        (e.g. 'camera' — handled separately).
        """
        widget_cls = _WIDGET_MAP.get(info.type)
        if widget_cls is None:
            logger.debug("No widget for panel type '%s' (id=%s)", info.type, info.id)
            return None

        try:
            widget = widget_cls(
                panel_id=info.id,
                panel_type=info.type,
                label=info.label or info.id,
                parent=parent,
            )
            widget.set_geometry(info.x, info.y, info.w, info.h)
            widget.setVisible(info.visible)
            logger.info(
                "Widget created: '%s' (type=%s, %dx%d at %d,%d)",
                info.id, info.type, info.w, info.h, info.x, info.y,
            )
            return widget
        except Exception:
            logger.exception("Failed to create widget for panel '%s'", info.id)
            return None
