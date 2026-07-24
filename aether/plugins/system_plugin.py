"""SystemPlugin — handles system-level commands (shutdown, ping, info)."""

from __future__ import annotations

import logging
import platform
import sys

from aether.core.command import Command
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.SystemPlugin")


class SystemPlugin(PluginBase):
    name = "system_plugin"

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="System",
            version="1.0",
            category="system",
            commands=["quit", "ping", "info"],
            description="System control and diagnostics",
        )

    def __init__(self) -> None:
        self._command_bus = None
        self._application = None

    def initialize(self, container: ServiceContainer) -> None:
        self._command_bus = container.resolve("command_bus")
        self._application = container.resolve("application")

        self._command_bus.register_handler("system.shutdown", self._handle_shutdown)
        self._command_bus.register_handler("system.ping", self._handle_ping)
        self._command_bus.register_handler("system.info", self._handle_info)

        logger.info("SystemPlugin registered commands: system.shutdown, system.ping, system.info")

    def shutdown(self) -> None:
        logger.info("SystemPlugin shutting down")

    def _handle_shutdown(self, command: Command) -> dict:
        """Shutdown the application."""
        logger.info("Shutdown command received from %s", command.source)
        if self._application:
            self._application.request_shutdown()
        return {"status": "ok", "message": "Shutdown requested"}

    def _handle_ping(self, command: Command) -> dict:
        """Echo back the params."""
        return {"status": "ok", "message": "pong", "echo": command.params}

    def _handle_info(self, command: Command) -> dict:
        """Return system info."""
        return {
            "status": "ok",
            "data": {
                "python_version": sys.version.split()[0],
                "platform": platform.platform(),
                "processor": platform.processor() or "unknown",
            }
        }