"""
AetherApp — the boot orchestrator for Phase A.

Boot sequence:
    1. Load configuration (creating defaults if missing).
    2. Configure logging based on that configuration.
    3. Create the ServiceContainer.
    4. Create the EventBus, ResultPipeline, and CommandBus; register them
       into the container so plugins can resolve them.
    5. Load and initialize plugins described in config.
    6. Report success.

This module intentionally does not know about cameras, gestures, or any UI
toolkit. Those arrive as plugins in later phases and only ever talk to the
container, never to this class directly.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from aether.config.loader import ConfigError, ConfigLoader
from aether.core.command_bus import CommandBus
from aether.core.event_bus import EventBus
from aether.core.plugin_loader import PluginLoader
from aether.core.result_pipeline import ResultPipeline
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.App")


class AetherAppBootError(Exception):
    """Raised when the application fails to boot. Wraps the underlying cause."""


class AetherApp:
    """Owns the lifecycle of the Aether runtime: boot, run, shutdown."""

    def __init__(self, config_path: str = "config/default.yaml", strict_plugins: bool = False) -> None:
        self.config_path = config_path
        self.strict_plugins = strict_plugins

        self.config: Optional[ConfigLoader] = None
        self.container: Optional[ServiceContainer] = None
        self.event_bus: Optional[EventBus] = None
        self.result_pipeline: Optional[ResultPipeline] = None
        self.command_bus: Optional[CommandBus] = None
        self.plugin_loader: Optional[PluginLoader] = None

        self._booted = False

    def boot(self) -> None:
        """Run the full boot sequence. Raises AetherAppBootError on any
        unrecoverable failure, with the original exception chained."""
        if self._booted:
            logger.warning("boot() called twice; ignoring second call.")
            return

        try:
            self.config = ConfigLoader(self.config_path)
            self.config.load()
        except ConfigError as exc:
            raise AetherAppBootError(f"Configuration failed to load: {exc}") from exc

        self._configure_logging()
        logger.info("=" * 60)
        logger.info(
            "Booting %s v%s",
            self.config.get("app.name", "Aether"),
            self.config.get("app.version", "unknown"),
        )
        logger.info("=" * 60)

        self.container = ServiceContainer()
        self.event_bus = EventBus()
        self.result_pipeline = ResultPipeline(self.event_bus)
        self.command_bus = CommandBus(self.result_pipeline)

        self.container.register_instance("config", self.config)
        self.container.register_instance("event_bus", self.event_bus)
        self.container.register_instance("result_pipeline", self.result_pipeline)
        self.container.register_instance("command_bus", self.command_bus)
        self.container.register_instance("application", self)

        self.plugin_loader = PluginLoader(self.container, strict_mode=self.strict_plugins)

        plugin_specs = self.config.get("plugins", [])
        plugins = self.plugin_loader.load_from_config(plugin_specs)
        self.plugin_loader.initialize_all(plugins)

        self._booted = True
        logger.info(
            "Aether booted successfully. %d plugin(s) active.",
            len(self.plugin_loader.loaded_plugins),
        )

    def shutdown(self) -> None:
        """Shut down all plugins and release resources. Safe to call even
        if boot() failed partway through."""
        if self.plugin_loader is not None:
            self.plugin_loader.shutdown_all()
        logger.info("Aether shutdown complete.")
        self._booted = False

    @property
    def is_booted(self) -> bool:
        return self._booted

    def _configure_logging(self) -> None:
        level_name = self.config.get("logging.level", "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        log_file = self.config.get("logging.file", "logs/aether.log")
        console_enabled = self.config.get("logging.console", True)

        handlers = []
        if console_enabled:
            handlers.append(logging.StreamHandler(sys.stdout))

        if log_file:
            log_path = Path(log_file)
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
            except OSError as exc:
                # Logging to a file is a nice-to-have, not a boot blocker.
                # Fall back to console-only and report why.
                print(f"[Aether] Could not open log file '{log_path}': {exc}", file=sys.stderr)

        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            handlers=handlers or [logging.StreamHandler(sys.stdout)],
            force=True,
        )
