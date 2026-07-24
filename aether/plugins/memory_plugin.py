"""MemoryPlugin — registers memory commands and provides MemoryService.

This plugin demonstrates:
1. Registering a domain service (MemoryService) during initialize
2. Registering command handlers that delegate to the service
3. Proper lifecycle: start/stop called by Application
"""

from __future__ import annotations

import logging

from aether.core.command import Command
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer
from aether.memory.service import MemoryService

logger = logging.getLogger("Aether.MemoryPlugin")


class MemoryPlugin(PluginBase):
    name = "memory_plugin"

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Memory",
            version="1.0",
            category="memory",
            commands=["remember", "recall", "forget", "list", "stats"],
            description="Spatial object and fact storage",
        )

    def __init__(self) -> None:
        self._service: MemoryService | None = None

    def initialize(self, container: ServiceContainer) -> None:
        command_bus = container.resolve("command_bus")
        application = container.resolve("application")

        # Create and register the service
        self._service = MemoryService()
        application.register_service("memory", self._service)

        # Register command handlers
        command_bus.register_handler("memory.remember", self._handle_remember)
        command_bus.register_handler("memory.recall", self._handle_recall)
        command_bus.register_handler("memory.forget", self._handle_forget)
        command_bus.register_handler("memory.list", self._handle_list)
        command_bus.register_handler("memory.stats", self._handle_stats)

        logger.info("MemoryPlugin registered commands: memory.remember, memory.recall, memory.forget, memory.list, memory.stats")

    def shutdown(self) -> None:
        logger.info("MemoryPlugin shutting down")

    # --- Command Handlers ---

    def _handle_remember(self, command: Command) -> dict:
        """Params: object_id, data (dict) OR key, fact (dict)"""
        params = command.params
        obj_id = params.get("object_id")
        key = params.get("key")

        if obj_id:
            data = params.get("data", {})
            self._service.remember_object(obj_id, data)
            return {"status": "ok", "object_id": obj_id}
        elif key:
            fact = params.get("fact", {})
            self._service.remember_fact(key, fact)
            return {"status": "ok", "key": key}
        else:
            return {"status": "error", "message": "Missing object_id or key"}

    def _handle_recall(self, command: Command) -> dict:
        """Params: object_id OR key"""
        params = command.params
        obj_id = params.get("object_id")
        key = params.get("key")

        if obj_id:
            result = self._service.recall_object(obj_id)
            if result:
                return {"status": "ok", "object": result}
            return {"status": "not_found", "object_id": obj_id}
        elif key:
            facts = self._service.recall_facts(key)
            return {"status": "ok", "key": key, "facts": facts}
        else:
            return {"status": "error", "message": "Missing object_id or key"}

    def _handle_forget(self, command: Command) -> dict:
        """Params: object_id OR key"""
        params = command.params
        obj_id = params.get("object_id")
        key = params.get("key")

        if obj_id:
            success = self._service.forget_object(obj_id)
            return {"status": "ok" if success else "not_found", "object_id": obj_id}
        elif key:
            count = self._service.clear_facts(key)
            return {"status": "ok", "key": key, "cleared": count}
        else:
            return {"status": "error", "message": "Missing object_id or key"}

    def _handle_list(self, command: Command) -> dict:
        """No params - returns all objects"""
        objects = self._service.list_objects()
        return {"status": "ok", "objects": objects, "count": len(objects)}

    def _handle_stats(self, command: Command) -> dict:
        """No params - returns storage stats"""
        return {"status": "ok", "stats": self._service.get_stats()}