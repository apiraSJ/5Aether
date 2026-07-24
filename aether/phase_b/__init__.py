"""
Legacy brain/interaction systems extracted from legacy/ modules
and adapted as plugins for Phase B.

Contains command handlers, context detection, and UI interaction plugins
that maintain compatibility with the legacy architecture.
"""

from .command_executor import CommandExecutor
from .context_manager_plugin import ContextManagerPlugin
from .notification_handler import NotificationHandler
from .history_handler import HistoryHandler
from .layout_handler import LayoutHandler
from .memory_service import MemoryService

__all__ = [
    "CommandExecutor",
    "ContextManagerPlugin",
    "NotificationHandler",
    "HistoryHandler",
    "LayoutHandler", 
    "MemoryService",
]
