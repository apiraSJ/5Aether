"""MemoryPlugin — lifecycle and EventBus integration for Memory Core.

Architecture:
    MemoryPlugin.initialize()
        → Creates MemoryManager
        → Registers memory commands in CommandRegistry
        → Subscribes to vision events for automatic spatial storage
        → Registers MemoryManager + MemoryService in DI container

    MemoryPlugin.start()
        → Opens database connection
        → Seeds demo memory on first boot (MemoryManager.seed_if_empty)
        → Publishes memory.ready
    
    MemoryPlugin.stop()
        → Closes database connection
        → Unsubscribes from events

Events published:
    memory.ready             — Memory system seeded and available (boot)
    memory.semantic.created  — New fact stored
    memory.semantic.updated  — Fact updated
    memory.semantic.deleted  — Fact deleted
    memory.episodic.created  — New event recorded
    memory.spatial.queried   — Spatial query performed
    memory.query.completed   — Search query performed
"""

from __future__ import annotations

import logging
from typing import Optional

from aether.core.command import Command
from aether.core.command_registry import CommandRegistry, CommandInfo
from aether.core.event_bus_v2 import Event
from aether.core.event_type import EventType
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer
from aether.memory.memory_manager import MemoryManager
from aether.services.memory_service import MemoryService

logger = logging.getLogger("Aether.MemoryPlugin")

_MEMORY_COMMANDS = [
    CommandInfo(
        name="memory.recall",
        description="Recall a memory record by key",
        category="memory",
        params_help="<key> [type]",
        examples=("recall bottle", "recall bottle semantic"),
    ),
    CommandInfo(
        name="memory.remember",
        description="Store a memory record",
        category="memory",
        params_help="<key> <value> [type]",
        examples=("remember bottle '{\"location\": \"desk\"}'",),
    ),
    CommandInfo(
        name="memory.forget",
        description="Delete memory records by key",
        category="memory",
        params_help="<key> [type]",
        aliases=("delete", "remove"),
    ),
    CommandInfo(
        name="memory.list",
        description="List all memory keys",
        category="memory",
        aliases=("ls",),
    ),
    CommandInfo(
        name="memory.search",
        description="Full-text search memory",
        category="memory",
        params_help="<query>",
    ),
    CommandInfo(
        name="memory.stats",
        description="Show memory statistics",
        category="memory",
    ),
    CommandInfo(
        name="memory.expire",
        description="Force expiration of stale records",
        category="memory",
    ),
    CommandInfo(
        name="memory.continue",
        description="Reconstruct your last work context (or start a new work session)",
        category="memory",
        params_help="[summary=<text>] [fact=<text>]",
        aliases=("continue_work",),
        examples=(
            "memory.continue",
            "memory.continue summary=\"C3 cleanup in the Aether repo\"",
            "memory.continue fact=\"Need to fix layout manager paths\"",
        ),
    ),
]


class MemoryPlugin(PluginBase):
    """Manages Memory Core lifecycle.

    Creates MemoryManager, registers commands, subscribes to events,
    and provides memory services to the rest of the system.
    """

    name = "memory_plugin"

    def __init__(self) -> None:
        self._container: Optional[ServiceContainer] = None
        self._event_bus = None
        self._command_bus = None
        self._memory: Optional[MemoryManager] = None
        self._service: Optional[MemoryService] = None
        self._db_path: str = "data/memory.db"

    @property
    def memory_service(self) -> Optional[MemoryService]:
        """The functional MemoryService (UI facade)."""
        return self._service

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Memory",
            version="1.0",
            category="memory",
            commands=[c.name for c in _MEMORY_COMMANDS],
            description="Memory Core: semantic, episodic, spatial, working memory",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._event_bus = container.resolve("event_bus")
        self._command_bus = container.resolve("command_bus")

        # Load config
        if container.has("config"):
            config = container.resolve("config")
            self._db_path = config.get("memory.db_path", "data/memory.db")

        # Create MemoryManager
        self._memory = MemoryManager(
            db_path=self._db_path,
            event_bus=self._event_bus,
        )

        # Register commands
        self._register_commands()

        # Register in DI container
        container.register_instance("memory_manager", self._memory)

        # Register functional MemoryService (UI facade)
        self._service = MemoryService(self._memory, event_bus=self._event_bus)
        container.register_instance("memory_service", self._service)

        # Subscribe to events
        self._subscribe_to_events()

        logger.info("MemoryPlugin initialized (db: %s)", self._db_path)

    def start(self) -> None:
        if self._memory:
            self._memory.open()
            seeded = self._memory.seed_if_empty()
            if seeded:
                logger.info("MemoryPlugin seeded %d demo record(s)", seeded)
        if self._event_bus:
            try:
                self._event_bus.publish(Event(type=EventType.MEMORY_READY, payload={
                    "seeded": self._memory.count() if self._memory else 0,
                }, source=self.name))
            except Exception as e:
                logger.warning("Failed to publish memory.ready: %s", e)
        # M1 Memory UX: after the first-boot seed, restore the user's last
        # work session so AI/UI can reconstruct context on return without
        # the user re-explaining it.
        if self._memory is not None and self._event_bus is not None:
            try:
                session = self._memory.get_latest_session()
                if session:
                    self._event_bus.publish(Event(
                        type=EventType.MEMORY_SESSION_RESTORED,
                        payload={"session": session},
                        source=self.name,
                    ))
            except Exception as e:
                logger.warning("Failed to restore work session: %s", e)
        logger.info("MemoryPlugin started")

    def is_ready(self) -> bool:
        """True when the memory manager exists and its database is open."""
        return self._memory is not None and self._memory.is_open

    def stop(self) -> None:
        if self._memory:
            self._memory.close()
        if self._event_bus:
            try:
                self._event_bus.unsubscribe("vision.object.detected", self._on_object_detected)
            except Exception:
                pass
        logger.info("MemoryPlugin stopped")

    # ── Command handlers ───────────────────────────────────────────

    def _register_commands(self) -> None:
        if not self._container:
            return

        # Register in CommandRegistry
        registry = None
        if self._container.has("command_registry"):
            registry = self._container.resolve("command_registry")
        else:
            registry = CommandRegistry()
            registry.initialize(self._container)

        for cmd_info in _MEMORY_COMMANDS:
            registry.register(cmd_info)

        # Register handlers on CommandBus
        if self._command_bus:
            self._command_bus.register_handler("memory.recall", self._handle_recall)
            self._command_bus.register_handler("memory.remember", self._handle_remember)
            self._command_bus.register_handler("memory.forget", self._handle_forget)
            self._command_bus.register_handler("memory.list", self._handle_list)
            self._command_bus.register_handler("memory.search", self._handle_search)
            self._command_bus.register_handler("memory.stats", self._handle_stats)
            self._command_bus.register_handler("memory.expire", self._handle_expire)
            self._command_bus.register_handler("memory.continue", self._handle_continue)

    def _handle_recall(self, command: Command) -> dict:
        key = command.params.get("key", "").strip()
        if not key:
            return {"message": "Usage: recall <key> [type]"}
        memory_type = command.params.get("type", "").strip() or None

        if not self._memory:
            return {"message": "Memory system not initialized"}

        result = self._memory.recall(key, memory_type)
        if result.found:
            lines = [f"Found {result.total} record(s):"]
            for r in result.records:
                lines.append(f"  [{r.memory_type}] {r.key} = {r.value}")
                if hasattr(r, "label") and r.label:
                    r_typed = r  # type: ignore
                    lines.append(f"    position: ({r_typed.x:.2f}, {r_typed.y:.2f}, {r_typed.z:.2f})")
                    lines.append(f"    confidence: {r_typed.confidence:.2f}")
            return {"message": "\n".join(lines)}
        return {"message": f"Memory '{key}' not found"}

    def _handle_remember(self, command: Command) -> dict:
        key = command.params.get("key", "").strip()
        value = command.params.get("value", "").strip()
        memory_type = command.params.get("type", "semantic").strip()

        if not key:
            return {"message": "Usage: remember <key> <value> [type]"}

        if not self._memory:
            return {"message": "Memory system not initialized"}

        import json
        try:
            parsed_value = json.loads(value) if value else key
        except json.JSONDecodeError:
            parsed_value = value

        record_id = self._memory.store(
            memory_type=memory_type,
            key=key,
            value=parsed_value,
        )
        return {"message": f"Stored '{key}' ({memory_type}) [id: {record_id[:8]}...]"}

    def _handle_forget(self, command: Command) -> dict:
        key = command.params.get("key", "").strip()
        memory_type = command.params.get("type", "").strip() or None

        if not key:
            return {"message": "Usage: forget <key> [type]"}

        if not self._memory:
            return {"message": "Memory system not initialized"}

        count = self._memory.forget(key, memory_type)
        return {"message": f"Deleted {count} record(s) for '{key}'"}

    def _handle_list(self, command: Command) -> dict:
        memory_type = command.params.get("type", "").strip() or None

        if not self._memory:
            return {"message": "Memory system not initialized"}

        keys = self._memory.list_keys(memory_type)
        if not keys:
            return {"message": "No memory records found"}
        return {"message": f"{len(keys)} keys:\n  " + "\n  ".join(keys)}

    def _handle_search(self, command: Command) -> dict:
        query = command.params.get("query", "").strip()
        if not query:
            return {"message": "Usage: search <query>"}

        if not self._memory:
            return {"message": "Memory system not initialized"}

        result = self._memory.search(query)
        if result.found:
            lines = [f"Search '{query}': {result.total} result(s):"]
            for r in result.records:
                lines.append(f"  [{r.memory_type}] {r.key} = {r.value}")
            return {"message": "\n".join(lines)}
        return {"message": f"No results for '{query}'"}

    def _handle_stats(self, command: Command) -> dict:
        if not self._memory:
            return {"message": "Memory system not initialized"}
        lines = [
            "=== Memory Stats ===",
            f"  Semantic:  {self._memory.count('semantic')} records",
            f"  Episodic:  {self._memory.count('episodic')} records",
            f"  Spatial:   {self._memory.count('spatial')} records",
            f"  Working:   {self._memory.count('working')} records",
            f"  Total:     {self._memory.count()} records",
        ]
        return {"message": "\n".join(lines)}

    def _handle_expire(self, command: Command) -> dict:
        if not self._memory:
            return {"message": "Memory system not initialized"}
        count = self._memory.expire_stale()
        return {"message": f"Expired {count} stale record(s)"}

    def _handle_continue(self, command: Command) -> dict:
        """Reconstruct the last work session, or start/update one.

        M1 Memory UX entry point:
            memory.continue                  → reconstruct last work session
            memory.continue summary="<text>" → start a new session (replaces)
            memory.continue fact="<text>"    → append a fact to the session
        """
        if not self._memory:
            return {"message": "Memory system not initialized"}

        summary = command.params.get("summary", "").strip()
        fact = command.params.get("fact", "").strip()

        if summary:
            self._memory.create_session(summary)
            return {"message": f"New work session started: {summary}"}

        if fact:
            if self._memory.append_session_fact(fact):
                return {"message": f"Remembered: {fact}"}
            self._memory.create_session(fact)
            return {"message": f"New work session started: {fact}"}

        session = self._memory.get_latest_session()
        if not session:
            return {
                "message": (
                    "No work session found. Start one by describing your task, "
                    "e.g.: memory.continue summary=\"C3 cleanup in the Aether repo\""
                )
            }

        parts = [f"You were working on {session['summary']}."]
        facts = session["key_facts"]
        if facts:
            parts.append("Remembered: " + "; ".join(facts) + ".")
        parts.append("Ready to continue.")
        return {"message": " ".join(parts)}

    # ── Event subscriptions ────────────────────────────────────────

    def _subscribe_to_events(self) -> None:
        if not self._event_bus:
            return
        try:
            self._event_bus.subscribe("vision.object.detected", self._on_object_detected)
            logger.debug("Subscribed to vision.object.detected")
        except Exception as e:
            logger.warning("Could not subscribe to vision events: %s", e)

    def _on_object_detected(self, event) -> None:
        """Auto-store detected objects into spatial memory."""
        if not self._memory or not self._memory.is_open:
            return

        objects = event.payload.get("objects", [])
        for obj in objects:
            label = obj.get("label", "unknown")
            confidence = obj.get("confidence", 0.0)
            bbox = obj.get("bbox", {})

            # Use bounding box center as position
            x = (bbox.get("x1", 0) + bbox.get("x2", 0)) / 2.0
            y = (bbox.get("y1", 0) + bbox.get("y2", 0)) / 2.0

            self._memory.store(
                memory_type="spatial",
                key=label,
                value=obj,
                context={"source": "vision", "confidence": confidence},
                x=x,
                y=y,
                z=0.0,
                confidence=confidence,
                label=label,
                ttl_seconds=3600,  # 1 hour TTL for vision detections
            )
