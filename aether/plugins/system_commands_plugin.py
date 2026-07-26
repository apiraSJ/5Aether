"""SystemCommandPlugin — registers system-level commands in CommandRegistry.

Commands registered:
  - system.help [category]     — show help
  - system.status              — system status
  - system.plugins             — list plugins
  - system.commands            — list all commands
  - system.ping                — health check
  - system.shutdown            — shutdown aether
  - cli.history                — command history
  - cli.clear                  — clear screen
"""

from __future__ import annotations

import logging
import os
import platform
import time
from typing import Any

from aether.core.command import Command
from aether.core.command_registry import CommandRegistry, CommandInfo
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.SystemCommands")

_SYSTEM_COMMANDS = [
    CommandInfo(
        name="system.help",
        description="Show help for a command or category",
        category="system",
        aliases=("h", "?"),
        params_help="[category]",
        examples=("help", "help memory", "help vision"),
    ),
    CommandInfo(
        name="system.status",
        description="Show system status",
        category="system",
        aliases=("st",),
    ),
    CommandInfo(
        name="system.plugins",
        description="List loaded plugins",
        category="system",
    ),
    CommandInfo(
        name="system.commands",
        description="List all registered commands",
        category="system",
    ),
    CommandInfo(
        name="system.ping",
        description="Health check",
        category="system",
        aliases=("p",),
    ),
    CommandInfo(
        name="system.shutdown",
        description="Shutdown Aether",
        category="system",
        aliases=("quit", "exit", "q"),
    ),
    CommandInfo(
        name="cli.history",
        description="Show command history",
        category="cli",
    ),
    CommandInfo(
        name="cli.clear",
        description="Clear the screen",
        category="cli",
        aliases=("cls",),
    ),
    CommandInfo(
        name="vision.scan",
        description="Scan the room with camera",
        category="vision",
    ),
    CommandInfo(
        name="memory.recall",
        description="Find a remembered object",
        category="memory",
        params_help="<query>",
        examples=("find phone", "where is my keys"),
    ),
    CommandInfo(
        name="memory.remember",
        description="Remember an object and its location",
        category="memory",
        params_help="<name> [at <location>]",
        examples=("remember bottle", "save keys at desk"),
    ),
    CommandInfo(
        name="memory.forget",
        description="Forget an object from memory",
        category="memory",
        params_help="<name>",
        aliases=("delete", "remove"),
    ),
    CommandInfo(
        name="memory.list",
        description="List all remembered objects",
        category="memory",
        aliases=("ls",),
    ),
]


class SystemCommandPlugin(PluginBase):
    """Registers system commands and their handlers in CommandRegistry + CommandBus."""

    name = "system_commands_plugin"

    def __init__(self) -> None:
        self._command_registry: CommandRegistry | None = None
        self._command_bus = None
        self._event_bus = None
        self._container: ServiceContainer | None = None
        self._boot_time: float = 0.0

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="System Commands",
            version="1.0",
            category="system",
            commands=[c.name for c in _SYSTEM_COMMANDS],
            description="System-level commands: help, status, plugins, quit",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._command_bus = container.resolve("command_bus")
        self._event_bus = container.resolve("event_bus")
        self._boot_time = time.time()

        # Create CommandRegistry if not already present
        if container.has("command_registry"):
            self._command_registry = container.resolve("command_registry")
        else:
            self._command_registry = CommandRegistry()
            self._command_registry.initialize(container)

        # Register all system commands in the registry
        for cmd_info in _SYSTEM_COMMANDS:
            self._command_registry.register(cmd_info)

        # Register handlers on CommandBus
        self._command_bus.register_handler("system.help", self._handle_help)
        self._command_bus.register_handler("system.status", self._handle_status)
        self._command_bus.register_handler("system.plugins", self._handle_plugins)
        self._command_bus.register_handler("system.commands", self._handle_commands)
        self._command_bus.register_handler("system.ping", self._handle_ping)
        self._command_bus.register_handler("system.shutdown", self._handle_shutdown)
        self._command_bus.register_handler("cli.history", self._handle_history)
        self._command_bus.register_handler("cli.clear", self._handle_clear)

        logger.info("System commands registered (%d commands)", len(_SYSTEM_COMMANDS))

    # ── Handlers ──────────────────────────────────────────────────────

    def _handle_help(self, command: Command) -> dict:
        category = command.params.get("category")
        help_text = self._command_registry.get_help(category)
        return {"message": help_text}

    def _handle_status(self, command: Command) -> dict:
        uptime = time.time() - self._boot_time
        status = {
            "uptime": f"{uptime:.0f}s",
            "platform": platform.system(),
            "commands_registered": self._command_registry.command_count,
        }
        if self._container and self._container.has("event_bus"):
            eb = self._container.resolve("event_bus")
            status["event_queue_depth"] = eb.queue_size()
        if self._container and self._container.has("command_bus"):
            cb = self._container.resolve("command_bus")
            status["commands_processed"] = cb.processed_count
        return {"message": "System status", **status}

    def _handle_plugins(self, command: Command) -> dict:
        if self._container and self._container.has("plugin_loader"):
            loader = self._container.resolve("plugin_loader")
            plugins = [
                {"name": getattr(p, "name", "?"), "type": type(p).__name__}
                for p in loader.loaded_plugins
            ]
            return {"message": f"{len(plugins)} plugins loaded", "plugins": plugins}
        return {"message": "Plugin loader not available"}

    def _handle_commands(self, command: Command) -> dict:
        categories = self._command_registry.get_categories()
        total = self._command_registry.command_count
        lines = [f"{total} commands registered across {len(categories)} categories:"]
        for cat in categories:
            cmds = self._command_registry.get_commands_in_category(cat)
            lines.append(f"  [{cat}] {', '.join(cmds)}")
        return {"message": "\n".join(lines)}

    def _handle_ping(self, command: Command) -> dict:
        return {"message": "pong", "timestamp": time.time()}

    def _handle_shutdown(self, command: Command) -> dict:
        if self._container and self._container.has("application"):
            self._container.resolve("application").request_shutdown()
        return {"message": "Shutting down..."}

    def _handle_history(self, command: Command) -> dict:
        if self._command_bus:
            recent = self._command_bus.get_recent(20)
            if not recent:
                return {"message": "No command history."}
            lines = []
            for cmd in recent:
                status_icon = "✓" if cmd.status == "COMPLETED" else "✗"
                lines.append(f"  {status_icon} {cmd.name} (source={cmd.source})")
            return {"message": "Recent commands:\n" + "\n".join(lines)}
        return {"message": "Command bus not available"}

    def _handle_clear(self, command: Command) -> dict:
        os.system("cls" if os.name == "nt" else "clear")
        return {"message": ""}
