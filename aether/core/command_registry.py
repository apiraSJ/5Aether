"""CommandRegistry — central service for command discovery, autocomplete, and help.

All input sources (CLI, GUI, Voice, API) query this service instead of
reading PluginMetadata directly. This decouples the UI layer from the
plugin system.

Responsibilities:
  - Register commands with metadata (name, description, category, aliases)
  - Autocomplete: partial string → list of matching commands
  - Help: per-category or full command reference
  - Aliases: map short aliases to canonical command names
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

from aether.core.service import IService
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.CommandRegistry")


@dataclass(frozen=True)
class CommandInfo:
    """Metadata for a single registered command."""

    name: str
    description: str = ""
    category: str = "general"
    aliases: tuple[str, ...] = ()
    params_help: str = ""
    examples: tuple[str, ...] = ()


class CommandRegistry(IService):
    """Central service for command discovery, autocomplete, and help.

    Plugins register their commands during initialize(). The CLI, GUI palette,
    and future input adapters query this registry — they never read
    PluginMetadata directly.
    """

    def __init__(self) -> None:
        self._commands: dict[str, CommandInfo] = {}
        self._aliases: dict[str, str] = {}  # alias -> canonical name
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        return "command_registry"

    def initialize(self, container: ServiceContainer) -> None:
        """Resolve dependencies. Called once during boot."""
        container.register_instance("command_registry", self)

    # ── Registration ──────────────────────────────────────────────────

    def register(self, info: CommandInfo) -> None:
        """Register a command with its metadata."""
        with self._lock:
            self._commands[info.name] = info
            for alias in info.aliases:
                self._aliases[alias.lower()] = info.name
            logger.debug(
                "Registered command: %s (category=%s, aliases=%s)",
                info.name, info.category, info.aliases,
            )

    def register_simple(
        self,
        name: str,
        description: str = "",
        category: str = "general",
        aliases: tuple[str, ...] = (),
    ) -> None:
        """Convenience: register without creating CommandInfo manually."""
        self.register(CommandInfo(
            name=name, description=description,
            category=category, aliases=aliases,
        ))

    def unregister(self, name: str) -> None:
        """Remove a command and its aliases."""
        with self._lock:
            info = self._commands.pop(name, None)
            if info:
                for alias in info.aliases:
                    self._aliases.pop(alias.lower(), None)

    # ── Lookup ────────────────────────────────────────────────────────

    def resolve(self, name: str) -> Optional[CommandInfo]:
        """Look up a command by name or alias. Returns None if not found."""
        with self._lock:
            canonical = self._aliases.get(name.lower(), name)
            return self._commands.get(canonical)

    def is_registered(self, name: str) -> bool:
        """Check if a command name or alias is registered."""
        with self._lock:
            canonical = self._aliases.get(name.lower(), name)
            return canonical in self._commands

    # ── Autocomplete ──────────────────────────────────────────────────

    def complete(self, partial: str, limit: int = 10) -> list[str]:
        """Return matching command names for tab-completion.

        Args:
            partial: The partial string to match (case-insensitive).
            limit: Maximum number of results.

        Returns:
            List of matching command names, sorted alphabetically.
        """
        lower = partial.lower()
        with self._lock:
            matches = []
            for name in sorted(self._commands):
                if name.lower().startswith(lower):
                    matches.append(name)
                    if len(matches) >= limit:
                        break
            if len(matches) < limit:
                for alias in sorted(self._aliases):
                    if alias.lower().startswith(lower):
                        canonical = self._aliases[alias]
                        if canonical not in matches:
                            matches.append(canonical)
                            if len(matches) >= limit:
                                break
            return matches

    def get_recent(self, limit: int = 10) -> list[str]:
        """Return the most recently registered commands ( insertion order )."""
        with self._lock:
            return list(self._commands.keys())[-limit:]

    # ── Help ──────────────────────────────────────────────────────────

    def get_help(self, category: Optional[str] = None) -> str:
        """Build a formatted help string.

        Args:
            category: If set, filter to commands in this category.
                      If None, show all categories.
        """
        with self._lock:
            if category:
                filtered = {
                    name: info for name, info in self._commands.items()
                    if info.category.lower() == category.lower()
                }
            else:
                filtered = dict(self._commands)

        if not filtered:
            return f"No commands found for category '{category}'." if category else "No commands registered."

        # Group by category
        categories: dict[str, list[CommandInfo]] = {}
        for info in filtered.values():
            categories.setdefault(info.category, []).append(info)

        lines = []
        for cat in sorted(categories):
            lines.append(f"\n  [{cat}]")
            lines.append("  " + "-" * 40)
            for info in sorted(categories[cat], key=lambda i: i.name):
                aliases_str = ""
                if info.aliases:
                    aliases_str = f" ({', '.join(info.aliases)})"
                lines.append(f"    {info.name:<24}{info.description}{aliases_str}")
                if info.params_help:
                    lines.append(f"      params: {info.params_help}")
                if info.examples:
                    for ex in info.examples:
                        lines.append(f"      example: {ex}")

        return "\n".join(lines)

    def get_categories(self) -> list[str]:
        """Return sorted list of unique categories."""
        with self._lock:
            return sorted({info.category for info in self._commands.values()})

    def get_commands_in_category(self, category: str) -> list[str]:
        """Return sorted command names in a category."""
        with self._lock:
            return sorted(
                name for name, info in self._commands.items()
                if info.category.lower() == category.lower()
            )

    # ── Status ────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return service status for health checks."""
        with self._lock:
            return {
                "service": self.name,
                "status": "running",
                "commands_registered": len(self._commands),
                "aliases_registered": len(self._aliases),
                "categories": self.get_categories(),
            }

    @property
    def command_count(self) -> int:
        with self._lock:
            return len(self._commands)
