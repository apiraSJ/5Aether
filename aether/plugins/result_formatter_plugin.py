"""ResultFormatterPlugin — formats command results for CLI output.

Subscribes to:
  - command.completed → print success message
  - command.failed → print error message
  - intent.failed → print hint
  - cli.output.displayed → print arbitrary text

This is the ONLY plugin that writes to stdout. All other plugins communicate
via events. This makes it trivial to swap CLI output for GUI, log file,
or network output in the future.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from aether.core.event_bus_v2 import Event
from aether.core.event_type import EventType
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.Formatter")


class ResultFormatterPlugin(PluginBase):
    """Formats command results for CLI output.

    Subscribes to EventBus events and writes formatted output to stdout.
    Color support: uses ANSI codes on TTY, plain text on piped output.
    """

    name = "result_formatter_plugin"

    def __init__(self) -> None:
        self._event_bus = None
        self._use_color = True
        self._cli_plugin = None
        # Commands too noisy to print on every completion
        self._silent_commands: set[str] = {
            "system.ping", "system.tick", "system.info",
            "vision.scan",
            "cursor.move", "cursor_click",
            "input.gesture",
        }
        # Prefixes for high-frequency commands (any cmd starting with these is silent)
        self._silent_prefixes: tuple[str, ...] = (
            "gesture_",
            "gesture.",
            "pinch_",
        )

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Result Formatter",
            version="1.0",
            category="output",
            description="Formats command results for CLI display",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._event_bus = container.resolve("event_bus")
        self._use_color = sys.stdout.isatty()

        # Subscribe to command lifecycle events
        self._event_bus.subscribe(EventType.COMMAND_COMPLETED, self._on_command_completed)
        self._event_bus.subscribe(EventType.COMMAND_FAILED, self._on_command_failed)
        self._event_bus.subscribe(EventType.INTENT_FAILED, self._on_intent_failed)
        self._event_bus.subscribe(EventType.CLI_OUTPUT_DISPLAYED, self._on_cli_output)

        logger.info("ResultFormatter initialized (color=%s)", self._use_color)

    # ── Event handlers ────────────────────────────────────────────────

    def _on_command_completed(self, event: Event) -> None:
        """Format successful command result. Skip silent/high-frequency commands."""
        cmd_name = event.payload.get("command", "")
        if cmd_name in self._silent_commands:
            return
        if any(cmd_name.startswith(p) for p in self._silent_prefixes):
            return
        result = event.payload.get("result")
        duration = event.payload.get("duration_ms", 0)

        msg = self._format_result(cmd_name, result, duration)
        if msg:
            self._print(msg, "green")

    def _on_command_failed(self, event: Event) -> None:
        """Format failed command result."""
        cmd_name = event.payload.get("command", "")
        error = event.payload.get("error", "Unknown error")

        self._print(f"  ✗ {cmd_name}: {error}", "red")

    def _on_intent_failed(self, event: Event) -> None:
        """Format unresolved intent."""
        hint = event.payload.get("hint", "Type 'help' for available commands.")
        self._print(f"  {hint}", "yellow")

    def _on_cli_output(self, event: Event) -> None:
        """Display arbitrary CLI output."""
        text = event.payload.get("text", "")
        color = event.payload.get("color", "white")
        if text:
            self._print(text, color)

    # ── Formatting ────────────────────────────────────────────────────

    def _format_result(self, cmd_name: str, result: Any, duration_ms: float) -> str:
        """Format a command result for display."""
        if result is None:
            return f"  ✓ {cmd_name} ({duration_ms:.0f}ms)"

        if isinstance(result, dict):
            return self._format_dict_result(cmd_name, result, duration_ms)

        if isinstance(result, str):
            return f"  ✓ {result}"

        return f"  ✓ {cmd_name}: {result}"

    def _format_dict_result(self, cmd_name: str, data: dict, duration_ms: float) -> str:
        """Format a dict result nicely."""
        lines = []

        if "message" in data:
            lines.append(f"  ✓ {data['message']}")
        elif "result" in data:
            inner = data["result"]
            if isinstance(inner, dict):
                for k, v in inner.items():
                    lines.append(f"    {k}: {v}")
            else:
                lines.append(f"  ✓ {inner}")
        else:
            for k, v in data.items():
                if k not in ("command_id", "command_name"):
                    lines.append(f"    {k}: {v}")

        if not lines:
            lines.append(f"  ✓ {cmd_name} completed")

        return "\n".join(lines)

    # ── Output ────────────────────────────────────────────────────────

    def _print(self, text: str, color: str = "white") -> None:
        """Print to stdout with optional ANSI color."""
        if self._use_color and color != "white":
            code = _COLORS.get(color, "")
            reset = "\033[0m" if code else ""
            print(f"{code}{text}{reset}")
        else:
            print(text)

        # Emit output event for logging/audit
        self._event_bus.publish(Event(
            type=EventType.CLI_OUTPUT_DISPLAYED,
            payload={"text": text, "color": color},
            source="formatter",
        ))


_COLORS = {
    "green": "\033[92m",
    "red": "\033[91m",
    "yellow": "\033[93m",
    "cyan": "\033[96m",
    "blue": "\033[94m",
    "magenta": "\033[95m",
    "white": "",
    "grey": "\033[90m",
}
