import logging
from typing import Dict, Type, Any, Optional
from abc import ABC, abstractmethod


class Plugin(ABC):
    @abstractmethod
    def initialize(self, config: dict) -> None:
        pass

    @abstractmethod
    def process(self, frame, **kwargs) -> Any:
        pass

    @abstractmethod
    def shutdown(self) -> None:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    def is_initialized(self) -> bool:
        return getattr(self, '_initialized', False)


class PluginManager:
    def __init__(self):
        self.logger = logging.getLogger("Aether.PluginManager")
        self._plugins: Dict[str, Plugin] = {}
        self._initialized = False

    def register(self, plugin: Plugin):
        name = plugin.name
        if name in self._plugins:
            self.logger.warning(f"Plugin '{name}' already registered, replacing")
        self._plugins[name] = plugin
        self.logger.info(f"Plugin '{name}' registered")

    def unregister(self, name: str):
        if name in self._plugins:
            plugin = self._plugins.pop(name)
            if plugin.is_initialized:
                plugin.shutdown()
            self.logger.info(f"Plugin '{name}' unregistered")

    def initialize_all(self, config: dict):
        for name, plugin in self._plugins.items():
            if not plugin.is_initialized:
                try:
                    plugin_config = config.get(name, {})
                    plugin.initialize(plugin_config)
                    self.logger.info(f"Plugin '{name}' initialized")
                except Exception as e:
                    self.logger.error(f"Failed to initialize plugin '{name}': {e}")

        self._initialized = True

    def process_all(self, frame, **kwargs) -> dict:
        results = {}
        for name, plugin in self._plugins.items():
            if plugin.is_initialized:
                try:
                    results[name] = plugin.process(frame, **kwargs)
                except Exception as e:
                    self.logger.error(f"Plugin '{name}' processing error: {e}")
                    results[name] = None
        return results

    def shutdown_all(self):
        for name, plugin in self._plugins.items():
            if plugin.is_initialized:
                try:
                    plugin.shutdown()
                    self.logger.info(f"Plugin '{name}' shut down")
                except Exception as e:
                    self.logger.error(f"Failed to shutdown plugin '{name}': {e}")
        self._initialized = False

    def get_plugin(self, name: str) -> Optional[Plugin]:
        return self._plugins.get(name)

    def list_plugins(self):
        return {name: plugin.is_initialized for name, plugin in self._plugins.items()}
