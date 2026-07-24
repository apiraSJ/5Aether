"""
SystemInfoPlugin — Phase A proof-of-life plugin.

Registers a single command, 'system.info', that reports basic runtime
information (Python version, platform, and CPU/memory usage if psutil is
available). This exists purely to prove that a plugin loaded from config can
resolve the CommandBus from the ServiceContainer and register a working
command handler, end to end, with no camera or UI involved.
"""

from __future__ import annotations

import logging
import platform
import sys

from aether.core.command import Command
from aether.core.command_result import CommandResult
from aether.core.plugin import PluginBase
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.SystemInfoPlugin")

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


class SystemInfoPlugin(PluginBase):
    name = "system_info_plugin"

    def initialize(self, container: ServiceContainer) -> None:
        command_bus = container.resolve("command_bus")
        command_bus.register("system.info", self._handle_system_info)
        command_bus.register("system.ping", self._handle_ping)
        logger.info("SystemInfoPlugin registered commands: system.info, system.ping")

    def shutdown(self) -> None:
        logger.info("SystemInfoPlugin shutting down (nothing to release).")

    def _handle_ping(self, command: Command) -> CommandResult:
        return CommandResult.ok(
            command_id=command.id,
            command_name=command.name,
            message="pong",
            data={"echo": command.params},
        )

    def _handle_system_info(self, command: Command) -> CommandResult:
        info = {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor() or "unknown",
        }

        if _PSUTIL_AVAILABLE:
            info["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            info["memory_percent"] = psutil.virtual_memory().percent
        else:
            info["cpu_percent"] = None
            info["memory_percent"] = None

        return CommandResult.ok(
            command_id=command.id,
            command_name=command.name,
            message="System info collected.",
            data=info,
            notification=None,
        )
