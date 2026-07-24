"""
PluginLoader — dynamically imports plugin classes described in configuration
and wires them into the ServiceContainer.

A plugin spec in config/default.yaml looks like:

    plugins:
      - module: "aether.plugins.system_info_plugin"
        class: "SystemInfoPlugin"
        enabled: true

By default a single misbehaving plugin does not crash the whole application:
its failure is logged and the app continues booting without it. Set
`strict_mode=True` when constructing PluginLoader if you want any plugin
failure to abort the boot instead (useful in CI / automated tests).
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List

from aether.core.plugin import PluginBase
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.PluginLoader")


class PluginLoadError(Exception):
    """Raised when a plugin cannot be imported, instantiated, or initialized."""


class PluginLoader:
    """Loads plugin classes from config specs and manages their lifecycle."""

    def __init__(self, container: ServiceContainer, strict_mode: bool = False) -> None:
        self._container = container
        self._strict_mode = strict_mode
        self._loaded_plugins: List[PluginBase] = []

    @property
    def loaded_plugins(self) -> List[PluginBase]:
        """Read-only view of the plugins currently loaded and initialized."""
        return list(self._loaded_plugins)

    def load_module(self, module_path: str, class_name: str) -> PluginBase:
        """Import `module_path`, fetch `class_name` from it, and instantiate it.

        Raises PluginLoadError with a clear, actionable message on any failure
        (missing module, missing class, class not a PluginBase subclass,
        or constructor raising).
        """
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise PluginLoadError(
                f"Could not import plugin module '{module_path}': {exc}"
            ) from exc

        plugin_class = getattr(module, class_name, None)
        if plugin_class is None:
            raise PluginLoadError(
                f"Module '{module_path}' has no attribute '{class_name}'."
            )

        if not (isinstance(plugin_class, type) and issubclass(plugin_class, PluginBase)):
            raise PluginLoadError(
                f"'{module_path}.{class_name}' must be a subclass of PluginBase."
            )

        try:
            instance = plugin_class()
        except Exception as exc:
            raise PluginLoadError(
                f"Constructing '{module_path}.{class_name}' raised an exception: {exc}"
            ) from exc

        return instance

    def load_from_config(self, plugin_specs: List[Dict[str, Any]]) -> List[PluginBase]:
        """Load every enabled plugin described in `plugin_specs`.

        Each spec must contain 'module' and 'class' keys; 'enabled' defaults
        to True if omitted. Disabled plugins are skipped entirely (not even
        imported).
        """
        loaded: List[PluginBase] = []

        for index, spec in enumerate(plugin_specs):
            if not isinstance(spec, dict):
                self._report_error(
                    f"Plugin spec at index {index} must be a mapping, got {type(spec).__name__}."
                )
                continue

            if not spec.get("enabled", True):
                logger.info("Skipping disabled plugin spec at index %d: %s", index, spec)
                continue

            module_path = spec.get("module")
            class_name = spec.get("class")
            if not module_path or not class_name:
                self._report_error(
                    f"Plugin spec at index {index} is missing 'module' and/or 'class': {spec}"
                )
                continue

            try:
                plugin = self.load_module(module_path, class_name)
            except PluginLoadError as exc:
                self._report_error(str(exc))
                continue

            loaded.append(plugin)

        self._loaded_plugins.extend(loaded)
        return loaded

    def initialize_all(self, plugins: List[PluginBase]) -> None:
        """Call initialize(container) on every plugin in order.

        Successfully initialized plugins are tracked for lifecycle calls
        (shutdown). A plugin that fails to initialize is logged and excluded
        from further lifecycle calls, unless strict_mode is enabled, in
        which case the exception propagates and aborts boot.
        """
        for plugin in list(plugins):
            try:
                plugin.initialize(self._container)
                logger.info("Initialized plugin '%s'", plugin.name)
                if plugin not in self._loaded_plugins:
                    self._loaded_plugins.append(plugin)
            except Exception as exc:
                message = f"Plugin '{plugin.name}' failed to initialize: {exc}"
                if self._strict_mode:
                    raise PluginLoadError(message) from exc
                logger.error(message)
                if plugin in self._loaded_plugins:
                    self._loaded_plugins.remove(plugin)

    def shutdown_all(self) -> None:
        """Call shutdown() on every successfully initialized plugin, in
        reverse order. Each plugin's failure is logged and does not prevent
        the remaining plugins from shutting down."""
        for plugin in reversed(self._loaded_plugins):
            try:
                plugin.shutdown()
                logger.info("Shut down plugin '%s'", plugin.name)
            except Exception:
                logger.exception("Plugin '%s' raised while shutting down.", plugin.name)
        self._loaded_plugins.clear()

    def _report_error(self, message: str) -> None:
        if self._strict_mode:
            raise PluginLoadError(message)
        logger.error(message)
