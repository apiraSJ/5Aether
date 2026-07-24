# aether/core/plugin_manager.py
"""
PluginManager — loads and manages Aether plugins through dependency injection.

Core services (EventBus, ConfigLoader, etc.) are registered on creation.
Plugins are loaded lazily when needed.
"""

import importlib
import logging
from typing import List, Dict, Any

from aether.core.plugin import PluginBase
from aether.core.service_container import ServiceContainer
from aether.core.plugin_manager import PluginManager

logger = logging.getLogger("Aether.PluginManager")


class PluginManager:
    """Manages plugin loading and lifecycle through DI container."""

    def __init__(self, container: ServiceContainer):
        self.container = container
        self.plugins: List[PluginBase] = []
        self.logger = logging.getLogger("Aether.PluginManager")
        self._initialize_core_services()

    def _initialize_core_services(self):
        """Register core services for all plugins to use."""
        event_bus = self.container.resolve("event_bus")
        command_bus = self.container.resolve("command_bus")
        result_pipeline = self.container.resolve("result_pipeline")
        
        self.container.register_instance("event_bus", event_bus)
        self.container.register_instance("command_bus", command_bus)
        self.container.register_instance("result_pipeline", result_pipeline)

    def load_plugins(self, plugin_dirs: List[str] = None) -> None:
        """Load plugins from disk and initialize them through DI."""
        if plugin_dirs is None:
            plugin_dirs = ["plugins"]

        for plugin_dir in plugin_dirs:
            for plugin_file in self._plugin_files(plugin_dir):
                try:
                    module_name = self._module_name(plugin_file)
                    module = importlib.import_module(module_name)

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, PluginBase)
                            and hasattr(attr, "name")
                        ):
                            self.plugins.append(attr)
                            self.logger.info(
                                "Loaded plugin: %s (%s)", attr.name, attr.__name__
                            )

                except Exception as e:
                    self.logger.error("Failed to load plugin %s: %s", plugin_file, e)

    def initialize_all(self, config: Dict[str, Any] = None) -> bool:
        """Initialize all plugins using the container."""
        try:
            for plugin in self.plugins:
                try:
                    plugin.initialize(self.container)
                    self.logger.info(
                        "Initialized plugin: %s", plugin.name
                    )
                except Exception as e:
                    self.logger.error(
                        "Plugin %s initialization failed: %s", plugin.name, e
                    )
                    return False
            return True
        except Exception as e:
            self.logger.error("Failed to initialize plugins: %s", e)
            return False

    def start_all(self) -> bool:
        """Start all plugins."""
        try:
            for plugin in self.plugins:
                # Plugins may have additional start methods, register them above
                pass
            return True
        except Exception as e:
            self.logger.error("Failed to start plugins: %s", e)
            return False

    def shutdown_all(self) -> None:
        """Shutdown all plugins gracefully."""
        for plugin in self.plugins:
            try:
                plugin.shutdown()
            except Exception as e:
                self.logger.error(
                    "Plugin %s shutdown failed: %s", plugin.name, e
                )

    def _plugin_files(self, plugin_dir: str) -> List[str]:
        """Find all Python files in plugin directories."""
        import os

        files = []
        if not os.path.exists(plugin_dir):
            return files

        for root, _, filenames in os.walk(plugin_dir):
            for filename in filenames:
                if filename.endswith(".py"):
                    files.append(os.path.join(root, filename))

        return files

    def _module_name(self, plugin_file: str) -> str:
        """Convert plugin file path to module name."""
        import os

        abs_path = os.path.abspath(plugin_file)
        plugin_root = os.path.abspath("aether")

        if abs_path.startswith(plugin_root):
            rel_path = os.path.relpath(abs_path, plugin_root)
            return rel_path[:-3].replace("/", ".")

        return plugin_file
