"""HistoryPlugin — registers HistoryService and wires it to EventBus."""

from __future__ import annotations

import logging

from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer
from aether.history.service import HistoryService

logger = logging.getLogger("Aether.HistoryPlugin")


class HistoryPlugin(PluginBase):
    name = "history_plugin"

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="History",
            version="1.0",
            category="system",
            description="Command history and audit trail",
        )

    def __init__(self) -> None:
        self._service: HistoryService | None = None

    def initialize(self, container: ServiceContainer) -> None:
        application = container.resolve("application")
        event_bus = container.resolve("event_bus")

        self._service = HistoryService()
        self._service.set_event_bus(event_bus)
        application.register_service("history", self._service)

        logger.info("HistoryPlugin registered (max %d entries)", 200)

    def shutdown(self) -> None:
        logger.info("HistoryPlugin shutting down")