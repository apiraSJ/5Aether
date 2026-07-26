"""PluginRegistry — discover, register, and instantiate plugins.

Supports:
  - Core plugins (built-in, registered by path)
  - External plugins (discovered from entry_points or plugin directories)

Usage:
    registry = PluginRegistry()
    registry.discover()  # scans entry_points
    registry.register("my_plugin", MyPlugin)
    plugin = registry.instantiate("my_plugin")
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger("Aether.PluginRegistry")


class PluginInfo:
    """Metadata about a registered plugin class."""

    __slots__ = ("name", "factory", "category", "version", "description")

    def __init__(
        self,
        name: str,
        factory: Callable[..., Any],
        category: str = "unknown",
        version: str = "0.0",
        description: str = "",
    ) -> None:
        self.name = name
        self.factory = factory
        self.category = category
        self.version = version
        self.description = description


class PluginRegistry:
    """Central registry for plugin discovery and instantiation.

    Replaces __init__.py exports with a proper registry pattern
    that supports external plugins via entry_points.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}

    def register(
        self,
        name: str,
        factory: Callable[..., Any],
        category: str = "unknown",
        version: str = "0.0",
        description: str = "",
    ) -> None:
        """Register a plugin class by name."""
        if name in self._plugins:
            logger.warning("Plugin '%s' already registered, overwriting", name)
        self._plugins[name] = PluginInfo(
            name=name, factory=factory, category=category,
            version=version, description=description,
        )
        logger.debug("Registered plugin: %s [%s]", name, category)

    def discover(self) -> int:
        """Discover plugins from setuptools entry_points.

        Entry point group: 'aether.plugins'
        Returns count of newly discovered plugins.
        """
        count = 0
        try:
            from importlib.metadata import entry_points
            eps = entry_points()
            plugin_eps = eps.select(group="aether.plugins") if hasattr(eps, "select") else eps.get("aether.plugins", [])

            for ep in plugin_eps:
                if ep.name not in self._plugins:
                    try:
                        factory = ep.load()
                        self.register(ep.name, factory, category="external")
                        count += 1
                    except Exception:
                        logger.exception("Failed to load plugin '%s'", ep.name)
        except ImportError:
            pass

        logger.info("Discovered %d external plugins", count)
        return count

    def instantiate(self, name: str, **kwargs) -> Any:
        """Create an instance of a registered plugin."""
        info = self._plugins.get(name)
        if info is None:
            raise KeyError(f"Plugin '{name}' not registered")
        return info.factory(**kwargs)

    def has(self, name: str) -> bool:
        return name in self._plugins

    def get_info(self, name: str) -> Optional[PluginInfo]:
        return self._plugins.get(name)

    @property
    def registered_names(self) -> list[str]:
        return sorted(self._plugins.keys())

    @property
    def count(self) -> int:
        return len(self._plugins)
