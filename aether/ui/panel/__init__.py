"""Aether Panel system — layout, registry, panel abstractions, and widgets."""

from aether.ui.panel.i_panel import IPanel
from aether.ui.panel.abstract_panel import AbstractPanel
from aether.ui.panel.panel_info import PanelInfo, PanelCapability
from aether.ui.panel.panel_registry import PanelRegistry
from aether.ui.panel.layout_manager import LayoutManager
from aether.ui.panel.theme_manager import ThemeManager
from aether.ui.panel.notification_manager import NotificationManager
from aether.ui.panel.memory_panel import MemoryPanel
from aether.ui.panel.vision_panel import VisionPanel
from aether.ui.panel.system_panel import SystemPanel

# Sprint 2: Panel Widget Framework
from aether.ui.panel.i_panel_widget import IPanelWidget
from aether.ui.panel.panel_widget import PanelWidget
from aether.ui.panel.widget_factory import WidgetFactory
from aether.ui.panel.workspace_widget import WorkspaceWidget

# Sprint 2A: Window Management
from aether.ui.panel.panel_session import PanelSession
from aether.ui.panel.panel_controller import PanelController
from aether.ui.panel.workspace_scene import WorkspaceScene, WindowManager

# Sprint 2: Concrete panel widgets
from aether.ui.panel.memory_widget import MemoryPanelWidget
from aether.ui.panel.ai_chat_widget import AIChatPanelWidget
from aether.ui.panel.tasks_widget import TasksPanelWidget
from aether.ui.panel.dashboard_widget import DashboardPanelWidget
from aether.ui.panel.baseline_widget import BaselinePanelWidget

__all__ = [
    "IPanel",
    "AbstractPanel",
    "PanelInfo",
    "PanelCapability",
    "PanelRegistry",
    "LayoutManager",
    "ThemeManager",
    "NotificationManager",
    "MemoryPanel",
    "VisionPanel",
    "SystemPanel",
    # Sprint 2
    "IPanelWidget",
    "PanelWidget",
    "WidgetFactory",
    "WorkspaceWidget",
    "MemoryPanelWidget",
    "AIChatPanelWidget",
    "TasksPanelWidget",
    "DashboardPanelWidget",
    "BaselinePanelWidget",
    # Sprint 2A
    "PanelSession",
    "PanelController",
    "WorkspaceScene",
    "WindowManager",
]
