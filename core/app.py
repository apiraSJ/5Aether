import logging
import threading
import time
from core.event_bus import EventBus, EventType
from core.settings import Settings
from core.plugin_manager import PluginManager


class AetherApp:
    def __init__(self, config_path: str = None):
        self.logger = logging.getLogger("Aether.App")
        self.settings = Settings(config_path)
        self.event_bus = EventBus()
        self.plugin_manager = PluginManager()
        self._running = False
        self._start_time = None

    def initialize(self):
        self.logger.info("Initializing Aether application...")
        self.event_bus.emit(EventType.SYSTEM_STARTUP, source="app")
        self.plugin_manager.initialize_all(self.settings.all)
        self._start_time = time.time()
        self._running = True
        self.logger.info("Aether application initialized")

    def run(self):
        self._running = True
        self.logger.info("Aether application running")
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.logger.info("Interrupt received")
        finally:
            self.shutdown()

    def shutdown(self):
        if not self._running:
            return
        self._running = False
        self.logger.info("Shutting down Aether...")
        self.plugin_manager.shutdown_all()
        self.event_bus.emit(EventType.SYSTEM_SHUTDOWN, source="app")
        self.logger.info("Aether shutdown complete")

    @property
    def uptime(self):
        if self._start_time:
            return time.time() - self._start_time
        return 0.0

    @property
    def is_running(self):
        return self._running
