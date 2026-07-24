# aether/core/app.py
"""AetherApp — boot orchestrator and entry point management.

Handles engine initialization, module management, and startup/shutdown lifecycle.
"""

import logging
import threading
import time
from typing import Dict, Any

from aether.core.service_container import ServiceContainer
from aether.core.plugin_manager import PluginManager
from aether.core.event_bus import EventBus
from aether.core.command_bus import CommandBus
from aether.core.result_pipeline import ResultPipeline
from aether.core.reasoning_service import ReasoningService
from aether.core.command import Command, CommandRegistry

logger = logging.getLogger("Aether.App")


class AetherApp:
    """AetherApp manages the application lifecycle and services."""

    def __init__(self, container: ServiceContainer = None):
        self.container = container or ServiceContainer()
        self.logger = logging.getLogger("Aether.App")
        self.plugin_manager = PluginManager(self.container)
        self.command_registry = CommandRegistry()
        self._running = False
        self._start_time = None

    def _initialize_core_services(self) -> None:
        """Initialize core services in the container."""
        event_bus = EventBus()
        result_pipeline = ResultPipeline()

        self.container.register_instance("event_bus", event_bus)
        self.container.register_instance("result_pipeline", result_pipeline)

        # Register ReasoningService as a plugin
        reasoning = ReasoningService(self.container)
        self.plugin_manager.plugins.append(reasoning)

    def initialize(self, config: Dict[str, Any] = None) -> bool:
        """Initialize the application and all plugins."""
        try:
            self._initialize_core_services()

            # Load and initialize plugins
            self.plugin_manager.load_plugins(["aether/plugins"])
            if not self.plugin_manager.initialize_all(config):
                self.logger.error("Plugin initialization failed")
                return False

            self._start_time = time.time()
            self._running = True
            self.logger.info("Aether application initialized")
            return True
        except Exception as e:
            self.logger.error(f"Application initialization failed: {e}")
            return False

    def run(self) -> None:
        """Run the application main loop."""
        self._running = True
        self.logger.info("Aether application running")

        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.logger.info("Interrupt received")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Shutdown the application and clean up."""
        if not self._running:
            return

        self._running = False
        self.logger.info("Shutting down Aether...")
        self.plugin_manager.shutdown_all()
        self._running = False
        self.logger.info("Aether shutdown complete")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def uptime(self) -> float:
        if self._start_time:
            return time.time() - self._start_time
        return 0.0


class Application:
    """Legacy alias for backward compatibility."""

    def __init__(self, container: ServiceContainer = None):
        self.container = container or ServiceContainer()
        self.logger = logging.getLogger("Aether.Application")

    def initialize(self, config: Dict[str, Any] = None) -> bool:
        """Initialize the application."""
        app = AetherApp(self.container)
        return app.initialize(config)

    def run(self) -> None:
        """Run the application."""
        app = AetherApp(self.container)
        app.run()

    def shutdown(self) -> None:
        """Shutdown the application."""
        app = AetherApp(self.container)
        app.shutdown()
