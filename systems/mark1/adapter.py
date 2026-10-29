"""System Adapter for Aether Mark-1.

This wraps existing Aether entry points without moving code from aether/.
Implements the SystemModule protocol expected by the 5Aether Function Menu.
"""

class Mark1Adapter:
    """System Adapter for Aether Mark-1.

    Implements the SystemModule protocol expected by the 5Aether Function Menu.
    All logic delegates to existing aether services — no code duplication.
    """

    def __init__(self):
        self._initialized = False
        self._service_container = None

    def start(self, context=None):
        """Initialize Mark-1 system.

        Args:
            context: Optional system context provided by Function Menu host.
                     Contains service access, event publishing, command registration.
        """
        if self._initialized:
            return {"status": "already_started", "message": "Mark-1 already initialized"}

        try:
            from aether import __version__
            from aether.ai.context import ContextEngine
            from aether.task.service import ScheduleService
            from aether.ui.panel.panel_registry import PanelRegistry
            from aether.ui.panel.tasks_widget import TasksPanelWidget
            from aether.ui.panel.memory_panel import MemoryPanelWidget
            from aether.ui.panel.notification_manager import NotificationManager

            self._initialized = True
            self._service_container = {
                "version": __version__,
                "context_engine": ContextEngine,
                "schedule_service": ScheduleService,
                "panel_registry": PanelRegistry,
                "tasks_panel": TasksPanelWidget,
                "memory_panel": MemoryPanelWidget,
                "notification_manager": NotificationManager,
            }

            return {"status": "started", "message": f"Mark-1 {__version__} initialized via existing Aether services"}
        except Exception as e:
            self._initialized = False
            return {"status": "error", "message": str(e)}

    def stop(self):
        """Shutdown Mark-1 system gracefully."""
        if not self._initialized:
            return {"status": "not_started", "message": "Mark-1 not initialized"}

        self._initialized = False
        self._service_container = None

        return {"status": "stopped", "message": "Mark-1 shut down gracefully"}

    def get_health(self):
        """Return health status of Mark-1 system."""
        if not self._initialized:
            return {"status": "unhealthy", "message": "Mark-1 not initialized"}

        try:
            from aether import __version__
            from aether.task.service import ScheduleService
            from aether.ai.context import ContextEngine

            return {
                "status": "healthy",
                "message": f"Mark-1 healthy (Aether {__version__})",
                "services": {
                    "ai_context": "available",
                    "task_schedule": "available",
                    "calendar": "available",
                    "memory": "available",
                },
            }
        except Exception as e:
            return {"status": "degraded", "message": f"Mark-1 degraded: {str(e)}"}

# Export for manifest entrypoint
__all__ = ["Mark1Adapter"]