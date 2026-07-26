"""IntentResolverPlugin — glue between raw input and CommandBus.

Subscribes to CLI_INPUT_RECEIVED events, resolves intent via registered
IIntentResolver instances, and dispatches commands through CommandBus.

Flow:
  CLI_INPUT_RECEIVED → resolve() → COMMAND_REQUESTED → CommandBus.dispatch()

This plugin is the single entry point for all intent resolution. CLI, Voice,
GUI palette, and Remote API all flow through here.
"""

from __future__ import annotations

import logging
from typing import Any

from aether.core.command import Command
from aether.core.event_bus_v2 import Event
from aether.core.event_type import EventType
from aether.core.intent_resolver import IntentResult
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.IntentResolver")


class IntentResolverPlugin(PluginBase):
    """Event-driven intent resolver. Bridges raw input events to CommandBus.

    Subscribes to CLI_INPUT_RECEIVED (and future INPUT_VOICE, etc.)
    and dispatches resolved commands.
    """

    name = "intent_resolver_plugin"

    def __init__(self) -> None:
        self._event_bus = None
        self._command_bus = None
        self._resolvers: list[Any] = []  # IIntentResolver instances
        self._confidence_threshold: float = 0.5

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Intent Resolver",
            version="1.0",
            category="intent",
            description="Resolves natural language input to commands via registered resolvers",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._event_bus = container.resolve("event_bus")
        self._command_bus = container.resolve("command_bus")

        # Collect all registered intent resolvers
        if container.has("intent_resolver.rule"):
            self._resolvers.append(container.resolve("intent_resolver.rule"))

        # Sort by priority (lower = first)
        self._resolvers.sort(key=lambda r: getattr(r, "priority", 50))

        # Subscribe to CLI input events
        self._event_bus.subscribe(
            EventType.CLI_INPUT_RECEIVED, self._on_cli_input
        )

        logger.info(
            "IntentResolver loaded with %d resolver(s): %s",
            len(self._resolvers),
            [getattr(r, "resolver_name", r.__class__.__name__) for r in self._resolvers],
        )

    # ── Event handlers ────────────────────────────────────────────────

    def _on_cli_input(self, event: Event) -> None:
        """Handle CLI_INPUT_RECEIVED. Resolve intent and dispatch command."""
        text = event.payload.get("text", "")
        context = event.payload.get("context", "")

        if not text:
            return

        result = self.resolve(text)
        if result:
            self._dispatch_command(result, context)
        else:
            # Unknown command — emit failed intent
            self._event_bus.publish(Event(
                type=EventType.INTENT_FAILED,
                payload={
                    "raw_input": text,
                    "reason": "No matching intent found",
                    "hint": "Type 'help' for available commands",
                },
                source="intent_resolver",
            ))
            logger.debug("Unresolved input: %s", text)

    # ── Resolution ────────────────────────────────────────────────────

    def resolve(self, user_input: str) -> IntentResult | None:
        """Try each resolver in priority order. Return first match above threshold."""
        for resolver in self._resolvers:
            try:
                result = resolver.resolve(user_input)
                if result and result.confidence >= self._confidence_threshold:
                    logger.debug(
                        "Resolved '%s' → %s (confidence=%.2f, source=%s)",
                        user_input, result.command_name,
                        result.confidence, result.source,
                    )
                    return result
            except Exception:
                logger.exception(
                    "Resolver %s failed on input: %s",
                    getattr(resolver, "resolver_name", "?"), user_input,
                )
        return None

    def _dispatch_command(self, intent: IntentResult, context: str = "") -> None:
        """Create a Command from IntentResult and dispatch through CommandBus."""
        cmd = Command(
            name=intent.command_name,
            source="cli",
            params=intent.params,
            context=context or None,
        )

        # Emit COMMAND_REQUESTED event (for logging/audit)
        self._event_bus.publish(Event(
            type=EventType.INTENT_RESOLVED,
            payload={
                "intent": intent.intent,
                "command": intent.command_name,
                "confidence": intent.confidence,
                "source": intent.source,
                "raw_input": intent.raw_input,
                "command_id": cmd.id,
            },
            source="intent_resolver",
        ))

        # Dispatch through CommandBus
        self._command_bus.dispatch(cmd)
        logger.debug("Dispatched command: %s (id=%s)", cmd.name, cmd.id)

    def add_resolver(self, resolver: Any) -> None:
        """Add a resolver at runtime (for dynamic registration)."""
        self._resolvers.append(resolver)
        self._resolvers.sort(key=lambda r: getattr(r, "priority", 50))
        logger.info("Added resolver: %s", getattr(resolver, "resolver_name", "?"))

    def set_threshold(self, threshold: float) -> None:
        """Adjust confidence threshold (0.0 - 1.0)."""
        self._confidence_threshold = max(0.0, min(1.0, threshold))
