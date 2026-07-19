import logging
from core.plugin_manager import Plugin
from vision.hand_tracker import HandTracker, HandResults


class HandPlugin(Plugin):
    def __init__(self):
        self._config = {}
        self._tracker = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "hand_plugin"

    def initialize(self, config: dict) -> None:
        self._config = config
        try:
            self._tracker = HandTracker(config)
            self._tracker.initialize()
            self._initialized = self._tracker.is_initialized
            logging.getLogger("Aether.HandPlugin").info("Hand tracking plugin initialized")
        except Exception as e:
            logging.getLogger("Aether.HandPlugin").error(f"Failed to initialize hand tracking: {e}")

    def process(self, frame, **kwargs) -> HandResults:
        if not self._initialized or self._tracker is None:
            return None
        try:
            return self._tracker.process(frame)
        except Exception as e:
            logging.getLogger("Aether.HandPlugin").error(f"Hand tracking error: {e}")
            return None

    def shutdown(self) -> None:
        if self._tracker:
            self._tracker.shutdown()
        self._initialized = False
