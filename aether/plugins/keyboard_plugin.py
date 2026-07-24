"""KeyboardInputPlugin — reads stdin and emits commands each tick.

Demonstrates TickablePlugin pattern: polls input each frame, emits Commands.
Non-blocking input using select (works on Windows too via msvcrt fallback).
"""

from __future__ import annotations

import logging
import sys
import select
from typing import Any

from aether.core.command import Command
from aether.core.plugin import TickablePlugin, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.KeyboardInputPlugin")


class KeyboardInputPlugin(TickablePlugin):
    name = "keyboard_input_plugin"

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Keyboard Input",
            version="1.0",
            category="input",
            description="Terminal stdin command input",
        )

    def __init__(self) -> None:
        self._command_bus = None
        self._running = False

    def initialize(self, container: ServiceContainer) -> None:
        self._command_bus = container.resolve("command_bus")
        self._container = container
        logger.info("KeyboardInputPlugin initialized")

    def start(self) -> None:
        """Start input polling."""
        self._running = True
        logger.info("KeyboardInputPlugin started - type commands (help for list)")

    def update(self, dt: float) -> None:
        """Poll stdin non-blocking, emit commands."""
        if not self._running or not self._command_bus:
            return

        # Non-blocking stdin check
        if self._has_input():
            line = sys.stdin.readline()
            if line:
                self._process_line(line.strip())

    def stop(self) -> None:
        self._running = False
        logger.info("KeyboardInputPlugin stopped")

    def shutdown(self) -> None:
        self.stop()

    # --- Input handling ---

    def _has_input(self) -> bool:
        """Check if stdin has data available (non-blocking)."""
        try:
            # Unix/Linux/macOS
            return select.select([sys.stdin], [], [], 0)[0] != []
        except (ImportError, OSError):
            # Windows fallback - msvcrt.kbhit() if available
            try:
                import msvcrt
                return msvcrt.kbhit()
            except ImportError:
                return False

    def _process_line(self, line: str) -> None:
        """Parse input line and dispatch command."""
        if not line:
            return

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        # Built-in commands
        if cmd in ("quit", "exit", "q"):
            self._command_bus.dispatch(Command(name="system.shutdown", source="keyboard"))
            return

        if cmd in ("help", "h", "?"):
            self._print_help()
            return

        # Memory commands
        if cmd == "remember":
            if len(args) >= 2:
                # remember object_id key=value ...
                obj_id = args[0]
                data = self._parse_kv(args[1:])
                self._command_bus.dispatch(
                    Command(name="memory.remember", source="keyboard", params={"object_id": obj_id, "data": data})
                )
            else:
                print("Usage: remember <object_id> key=value ...")
            return

        if cmd == "recall":
            if len(args) >= 1:
                # recall object_id OR recall --key fact_key
                if args[0] == "--key" and len(args) >= 2:
                    self._command_bus.dispatch(
                        Command(name="memory.recall", source="keyboard", params={"key": args[1]})
                    )
                else:
                    self._command_bus.dispatch(
                        Command(name="memory.recall", source="keyboard", params={"object_id": args[0]})
                    )
            else:
                print("Usage: recall <object_id>  OR  recall --key <fact_key>")
            return

        if cmd == "forget":
            if len(args) >= 1:
                if args[0] == "--key" and len(args) >= 2:
                    self._command_bus.dispatch(
                        Command(name="memory.forget", source="keyboard", params={"key": args[1]})
                    )
                else:
                    self._command_bus.dispatch(
                        Command(name="memory.forget", source="keyboard", params={"object_id": args[0]})
                    )
            else:
                print("Usage: forget <object_id>  OR  forget --key <fact_key>")
            return

        if cmd == "list":
            self._command_bus.dispatch(Command(name="memory.list", source="keyboard"))
            return

        if cmd == "stats":
            self._command_bus.dispatch(Command(name="memory.stats", source="keyboard"))
            return

        # System commands
        if cmd == "ping":
            self._command_bus.dispatch(Command(name="system.ping", source="keyboard", params={"echo": " ".join(args)}))
            return

        if cmd == "info":
            self._command_bus.dispatch(Command(name="system.info", source="keyboard"))
            return

        print(f"Unknown command: {cmd}. Type 'help' for list.")

    def _parse_kv(self, args: list[str]) -> dict:
        """Parse key=value pairs."""
        result = {}
        for arg in args:
            if "=" in arg:
                k, v = arg.split("=", 1)
                # Try to parse as int/float/bool
                result[k] = self._parse_value(v)
        return result

    def _parse_value(self, v: str) -> Any:
        """Parse string to appropriate Python type."""
        if v.lower() in ("true", "false"):
            return v.lower() == "true"
        try:
            if "." in v:
                return float(v)
            return int(v)
        except ValueError:
            return v

    def _print_help(self) -> None:
        # Build help from plugin metadata
        lines = ["Aether Command Reference", "=" * 40]

        # Collect commands by category from loaded plugins
        categories: dict[str, list[tuple[str, str]]] = {}
        categories["system"] = [("help", "Show this help"), ("quit", "Shutdown Aether")]

        try:
            app = self._container.resolve("application")
            for plugin in app.plugin_loader.loaded_plugins:
                meta = plugin.metadata
                cat = meta.category or "general"
                for cmd in meta.commands:
                    categories.setdefault(cat, []).append((cmd, ""))
        except Exception:
            pass

        for cat in ["memory", "system", "input", "ui", "general"]:
            cmds = categories.get(cat)
            if not cmds:
                continue
            lines.append("")
            lines.append(f"{cat.upper()}")
            lines.append("-" * 30)
            for cmd_name, desc in cmds:
                desc_str = f"  - {desc}" if desc else ""
                lines.append(f"  {cmd_name}{desc_str}")

        lines.append("")
        print("\n".join(lines))


# Convenience for running without full app
if __name__ == "__main__":
    import time
    plugin = KeyboardInputPlugin()
    # Mock command bus for demo
    class MockBus:
        def dispatch(self, cmd):
            print(f"[DISPATCH] {cmd.name} {cmd.params}")
    plugin._command_bus = MockBus()
    plugin.start()
    try:
        while True:
            plugin.update(1/30)
            time.sleep(1/30)
    except KeyboardInterrupt:
        plugin.stop()