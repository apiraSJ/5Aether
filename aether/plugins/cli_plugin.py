"""CLIPlugin — interactive command-line interface for Aether.

Event-driven architecture:
  - User input → CLI_INPUT_RECEIVED event
  - IntentResolver resolves → COMMAND_REQUESTED event
  - CommandBus executes → result flows through ResultPipeline
  - ResultFormatter displays → CLI_OUTPUT_DISPLAYED event

The CLI never calls IntentResolver or CommandBus directly.

Features:
  - Readline with tab-completion (via CommandRegistry)
  - Command history navigation (up/down arrows)
  - Context-aware prompt: aether [vision]>
  - Ctrl+C cancels current input, Ctrl+D shuts down
"""

from __future__ import annotations

import logging
import os
import readline
import sys
import threading
from collections import deque
from typing import Any, Optional

from aether.core.command import Command
from aether.core.command_registry import CommandRegistry
from aether.core.event_bus_v2 import Event
from aether.core.event_type import EventType
from aether.core.plugin import TickablePlugin, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.CLI")

_HISTORY_MAX = 200


class CLIPlugin(TickablePlugin):
    """Interactive CLI interface. Reads stdin, emits CLI_INPUT_RECEIVED events.

    Uses CommandRegistry for autocomplete and help. Never touches IntentResolver
    or CommandBus directly — everything flows through events.
    """

    name = "cli_plugin"

    def __init__(self) -> None:
        self._event_bus = None
        self._command_registry: Optional[CommandRegistry] = None
        self._command_bus = None
        self._container: Optional[ServiceContainer] = None

        # Prompt state
        self._context: str = ""
        self._running = False
        self._reader_thread: Optional[threading.Thread] = None

        # History
        self._history: deque[str] = deque(maxlen=_HISTORY_MAX)
        self._history_index: int = -1

        # Last command for repeat-on-empty
        self._last_command: str = ""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="CLI",
            version="1.0",
            category="input",
            commands=["help", "quit", "exit", "history", "clear", "status", "plugins"],
            description="Interactive command-line interface",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._event_bus = container.resolve("event_bus")
        self._command_bus = container.resolve("command_bus")

        if container.has("command_registry"):
            self._command_registry = container.resolve("command_registry")
        else:
            self._command_registry = CommandRegistry()
            self._command_registry.initialize(container)

        self._setup_readline()
        logger.info("CLI initialized (prompt: %s)", self._get_prompt())

    def start(self) -> None:
        """Start the CLI reader thread."""
        self._running = True
        self._reader_thread = threading.Thread(
            target=self._read_loop, daemon=True, name="cli-reader"
        )
        self._reader_thread.start()
        logger.info("CLI started — type 'help' for commands")

    def update(self, dt: float) -> None:
        """TickablePlugin required but CLI is event-driven, not polled."""
        pass

    def stop(self) -> None:
        """Signal the reader thread to exit."""
        self._running = False
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2.0)

    def shutdown(self) -> None:
        self.stop()

    # ── Readline setup ────────────────────────────────────────────────

    def _setup_readline(self) -> None:
        """Configure readline with tab-completion from CommandRegistry."""
        readline.parse_and_bind("tab: complete")
        readline.set_completer(self._completer)
        readline.set_completer_delims(" \t\n")

        # Load history if exists
        history_path = os.path.expanduser("~/.aether_cli_history")
        try:
            readline.read_history_file(history_path)
        except FileNotFoundError:
            pass

        # Save history on exit
        import atexit
        atexit.register(self._save_history)

    def _completer(self, text: str, state: int) -> Optional[str]:
        """Tab-completion callback. Returns matching commands from registry."""
        if state == 0:
            # First call — build match list
            if text:
                self._completions = self._command_registry.complete(text, limit=20)
            else:
                # Empty input — show all commands
                self._completions = self._command_registry.complete("", limit=50)

        if state < len(self._completions):
            return self._completions[state]
        return None

    def _save_history(self) -> None:
        """Persist readline history to disk."""
        history_path = os.path.expanduser("~/.aether_cli_history")
        try:
            readline.write_history_file(history_path)
        except Exception:
            pass

    # ── Read loop (runs in thread) ────────────────────────────────────

    def _read_loop(self) -> None:
        """Main read loop. Reads from stdin and emits CLI_INPUT_RECEIVED events."""
        while self._running:
            try:
                prompt = self._get_prompt()
                # Use sys.stdin for non-blocking check
                if sys.stdin.isatty():
                    line = input(prompt)
                else:
                    # Non-interactive mode (piped input)
                    line = sys.stdin.readline()
                    if not line:
                        break
                    line = line.rstrip("\n")

                self._handle_input(line)

            except EOFError:
                logger.info("CLI: EOF received, shutting down...")
                self._running = False
                if self._container and self._container.has("application"):
                    self._container.resolve("application").request_shutdown()
                break
            except KeyboardInterrupt:
                print("\n^C — type 'quit' to exit")
                continue
            except Exception:
                logger.exception("CLI read error")
                continue

    def _handle_input(self, line: str) -> None:
        """Process a single line of input."""
        text = line.strip()

        # Empty line — repeat last command
        if not text and self._last_command:
            text = self._last_command
        elif text:
            self._last_command = text

        if not text:
            return

        # Add to history
        self._history.append(text)
        self._history_index = -1

        # Emit CLI_INPUT_RECEIVED event — IntentResolver will pick this up
        self._event_bus.publish(Event(
            type=EventType.CLI_INPUT_RECEIVED,
            payload={"text": text, "context": self._context},
            source="cli",
        ))

    # ── Public API (for ResultFormatter to call) ──────────────────────

    def set_context(self, context: str) -> None:
        """Update the prompt context, e.g. 'vision', 'memory'."""
        self._context = context
        logger.debug("CLI context changed to: %s", context or "default")

    def get_history(self, limit: int = 20) -> list[str]:
        """Return the last N commands from history."""
        return list(self._history)[-limit:]

    def get_prompt_context(self) -> str:
        return self._context

    # ── Helpers ───────────────────────────────────────────────────────

    def _get_prompt(self) -> str:
        """Build the prompt string with context."""
        if self._context:
            return f"aether [{self._context}]> "
        return "aether> "
