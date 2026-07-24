"""AetherApplication — the single orchestrator for Boot → Tick → Shutdown.

This class owns the lifecycle. It coordinates:
  - CommandBus.update()    : process pending commands
  - Services.update(dt)    : domain logic per tick
  - Plugins.update(dt)     : input polling per tick
  - EventBus.flush()       : deliver queued events per tick

It NEVER calls domain logic directly. No imports from memory/, reasoning/, spatial/.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
import types
from pathlib import Path
from typing import Any, Optional

from aether.config.loader import ConfigError, ConfigLoader
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import EventBus
from aether.core.plugin_loader import PluginLoader
from aether.core.result_pipeline import ResultPipeline
from aether.core.service_container import ServiceContainer
from aether.core.service import IService

logger = logging.getLogger("Aether.Application")


class ApplicationBootError(Exception):
    """Raised when the application fails to boot. Wraps the underlying cause."""


class AetherApplication:
    """Owns the Aether runtime lifecycle: boot → tick loop → shutdown."""

    def __init__(
        self,
        config_path: str = "config/default.yaml",
        strict_plugins: bool = False,
    ) -> None:
        self.config_path = config_path
        self.strict_plugins = strict_plugins

        # Core infrastructure (set during boot)
        self.config: Optional[ConfigLoader] = None
        self.container: Optional[ServiceContainer] = None
        self.event_bus: Optional[EventBus] = None
        self.result_pipeline: Optional[ResultPipeline] = None
        self.command_bus: Optional[CommandBus] = None
        self.plugin_loader: Optional[PluginLoader] = None

        # Domain services (registered by plugins during initialize)
        self._services: list[IService] = []

        # Lifecycle state
        self._booted = False
        self._running = False
        self._shutdown_requested = False

        # Timing
        self._tick_rate = 30  # Hz, configurable via config
        self._last_tick_time: float = 0.0

    # ----------------------------------------------------------------------
    # Public lifecycle API
    # ----------------------------------------------------------------------

    def boot(self) -> None:
        """Run the full boot sequence. Raises ApplicationBootError on failure.

        Steps:
          1. Load configuration
          2. Configure logging
          3. Create DI container
          4. Create core infrastructure (EventBus, ResultPipeline, CommandBus)
          5. Register core services into container
          6. Load and initialize plugins from config
          7. Call start() on all registered services
          8. Call start() on all tickable plugins
        """
        if self._booted:
            logger.warning("boot() called twice; ignoring second call.")
            return

        try:
            self.config = ConfigLoader(self.config_path)
            self.config.load()
        except ConfigError as exc:
            raise ApplicationBootError(f"Configuration failed to load: {exc}") from exc

        self._configure_logging()
        self._log_boot_banner()

        # 3. DI Container
        self.container = ServiceContainer()

        # 4. Core infrastructure
        self.event_bus = EventBus(queued=True)  # Phase B: queued mode
        self.result_pipeline = ResultPipeline(self.event_bus)
        self.command_bus = CommandBus(result_pipeline=self.result_pipeline, container=self.container, event_bus=self.event_bus)

        # Register core infrastructure into DI container
        self.container.register_instance("config", self.config)
        self.container.register_instance("event_bus", self.event_bus)
        self.container.register_instance("result_pipeline", self.result_pipeline)
        self.container.register_instance("command_bus", self.command_bus)
        self.container.register_instance("application", self)

        # 5. Plugin system
        self.plugin_loader = PluginLoader(self.container, strict_mode=self.strict_plugins)

        plugin_specs = self.config.get("plugins", [])
        plugins = self.plugin_loader.load_from_config(plugin_specs)
        self.plugin_loader.initialize_all(plugins)

        # 6. Discover and start services (plugins register them during initialize)
        self._discover_services()

        # 7. Start services (domain logic initialization)
        for service in self._services:
            try:
                service.start()
                logger.debug("Started service: %s", service.__class__.__name__)
            except Exception:
                logger.exception("Service %s failed to start", service.__class__.__name__)
                if self.strict_plugins:
                    raise

        # 8. Start tickable plugins (input capture threads, etc.)
        self._start_tickable_plugins()

        self._booted = True
        self._last_tick_time = time.perf_counter()
        logger.info("Aether booted successfully. %d plugin(s) active.", len(self.plugin_loader.loaded_plugins))

    def run(self) -> int:
        """Run the main loop until shutdown is requested.

        Returns exit code (0 = normal, 1 = boot error, 130 = SIGINT).
        """
        if not self._booted:
            self.boot()

        self._install_signal_handlers()
        self._running = True

        logger.info("Aether main loop starting at %d Hz", self._tick_rate)

        try:
            while self._running and not self._shutdown_requested:
                self.tick()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received.")
            return 130
        except Exception:
            logger.exception("Unhandled exception in main loop")
            return 1
        finally:
            self.shutdown()

        return 0

    def tick(self) -> None:
        """Single frame tick. Called repeatedly by run().

        Order matters:
          1. Calculate dt
          2. CommandBus.update() - process any pending commands
          3. Services.update(dt) - domain logic
          4. Plugins.update(dt) - input polling
          5. EventBus.flush() - deliver queued events (deterministic ordering)
        """
        now = time.perf_counter()
        dt = now - self._last_tick_time
        self._last_tick_time = now

        # 1. Process command queue
        if self.command_bus:
            self.command_bus.update()

        # 2. Domain services
        for service in self._services:
            try:
                service.update(dt)
            except Exception:
                logger.exception("Service %s update failed", service.__class__.__name__)

        # 3. Tickable plugins (input adapters)
        self._update_tickable_plugins(dt)

        # 4. Flush event queue (deterministic, ordered delivery)
        if self.event_bus:
            self.event_bus.flush()

        # 5. Rate limiting (simple sleep to target Hz)
        self._rate_limit(dt)

    def shutdown(self) -> None:
        """Graceful shutdown. Safe to call multiple times."""
        if not self._booted and not self._running:
            return

        logger.info("Shutting down Aether...")

        self._running = False
        self._shutdown_requested = True

        # 1. Stop tickable plugins (input threads)
        self._stop_tickable_plugins()

        # 2. Stop services (persist, cleanup)
        for service in reversed(self._services):
            try:
                service.stop()
                logger.debug("Stopped service: %s", service.__class__.__name__)
            except Exception:
                logger.exception("Service %s stop failed", service.__class__.__name__)

        # 3. Final event flush (drain any remaining)
        if self.event_bus:
            flushed = self.event_bus.flush()
            if flushed:
                logger.debug("Final flush delivered %d events", flushed)

        # 4. Shutdown plugins (reverse init order)
        if self.plugin_loader:
            self.plugin_loader.shutdown_all()

        self._booted = False
        logger.info("Aether shutdown complete.")

    def request_shutdown(self) -> None:
        """Request graceful shutdown from any thread."""
        self._shutdown_requested = True

    # ----------------------------------------------------------------------
    # Properties
    # ----------------------------------------------------------------------

    @property
    def is_booted(self) -> bool:
        return self._booted

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def tick_rate(self) -> int:
        return self._tick_rate

    @tick_rate.setter
    def tick_rate(self, hz: int) -> None:
        if hz < 1:
            raise ValueError("tick_rate must be >= 1")
        self._tick_rate = hz

    # ----------------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------------

    def _discover_services(self) -> None:
        """Find all IService instances registered in the container."""
        if not self.container:
            return

        # Services register themselves via container.register_instance("service.name", service)
        # during plugin.initialize(). We find them by scanning.
        # Convention: service keys start with "service."
        for key, instance in self.container._instances.items():  # type: ignore[attr-defined]
            if key.startswith("service.") and hasattr(instance, "update"):
                if instance not in self._services:
                    self._services.append(instance)
                    logger.debug("Discovered service: %s", key)

    def _start_tickable_plugins(self) -> None:
        """Call start() on plugins that implement TickablePlugin."""
        from aether.core.plugin import TickablePlugin

        if not self.plugin_loader:
            return

        for plugin in self.plugin_loader.loaded_plugins:
            if isinstance(plugin, TickablePlugin):
                try:
                    plugin.start()
                    logger.debug("Started tickable plugin: %s", plugin.name)
                except Exception:
                    logger.exception("Tickable plugin %s start failed", plugin.name)
                    if self.strict_plugins:
                        raise

    def _update_tickable_plugins(self, dt: float) -> None:
        """Call update(dt) on plugins that implement TickablePlugin."""
        from aether.core.plugin import TickablePlugin

        if not self.plugin_loader:
            return

        for plugin in self.plugin_loader.loaded_plugins:
            if isinstance(plugin, TickablePlugin):
                try:
                    plugin.update(dt)
                except Exception:
                    logger.exception("Tickable plugin %s update failed", plugin.name)

    def _stop_tickable_plugins(self) -> None:
        """Call stop() on plugins that implement TickablePlugin."""
        from aether.core.plugin import TickablePlugin

        if not self.plugin_loader:
            return

        for plugin in reversed(self.plugin_loader.loaded_plugins):
            if isinstance(plugin, TickablePlugin):
                try:
                    plugin.stop()
                    logger.debug("Stopped tickable plugin: %s", plugin.name)
                except Exception:
                    logger.exception("Tickable plugin %s stop failed", plugin.name)

    def _rate_limit(self, dt: float) -> None:
        """Sleep to maintain target tick rate."""
        target_dt = 1.0 / self._tick_rate
        remaining = target_dt - dt
        if remaining > 0:
            time.sleep(remaining)

    def _install_signal_handlers(self) -> None:
        def _handler(signum: int, frame: Optional[types.FrameType]) -> None:
            logger.info("Received signal %s, requesting shutdown...", signum)
            self.request_shutdown()

        signal.signal(signal.SIGINT, _handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handler)

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
                print(f"[Aether] Could not open log file '{log_path}': {exc}", file=sys.stderr)

        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            handlers=handlers or [logging.StreamHandler(sys.stdout)],
            force=True,
        )

    def _log_boot_banner(self) -> None:
        app_name = self.config.get("app.name", "Aether")
        app_version = self.config.get("app.version", "unknown")
        logger.info("=" * 60)
        logger.info("Booting %s v%s", app_name, app_version)
        logger.info("=" * 60)

    # ----------------------------------------------------------------------
    # Service registration (called by plugins during initialize)
    # ----------------------------------------------------------------------

    def register_service(self, name: str, service: IService) -> None:
        """Plugins call this during initialize() to register domain services.

        The service will receive start() after all plugins initialize,
        update(dt) every tick, and stop() during shutdown.
        """
        if not self.container:
            raise RuntimeError("Cannot register service before boot()")
        key = f"service.{name}"
        self.container.register_instance(key, service)
        if service not in self._services:
            self._services.append(service)
        logger.debug("Registered service: %s", key)