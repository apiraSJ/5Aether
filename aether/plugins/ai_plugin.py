"""AIPlugin — lifecycle and integration for the AI chat service.

Architecture:
    AIPlugin.initialize()
        → Loads config/ai.yaml (merged over the base config via ConfigLoader)
        → Creates AIService (EchoProvider in Phase 1.5)
        → Creates ToolRegistry (explicit whitelist) + ToolExecutor (CommandBus
          boundary) and wires them into AIService
        → Registers ai.chat in CommandRegistry
        → Registers ai.chat handler on CommandBus
        → Registers AIService in DI container

    AIPlugin handles `ai.chat` commands dispatched by the AI Chat panel
    widget, CLI, or voice — it is the single owner of the assistant command
    (previously an echo bot living inside GUIPlugin).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from aether.ai.context import ContextEngine
from aether.ai.intent import IntentReasoner, RuleBasedIntentClassifier
from aether.ai.memory import DefaultMemoryRetriever
from aether.ai.models import AIState
from aether.ai.provider import AIProvider, ProviderError
from aether.ai.providers import create_provider
from aether.ai.service import AIService
from aether.ai.tools import ToolExecutor, ToolRegistry
from aether.config.loader import ConfigLoader
from aether.core.ai_worker import AIWorker
from aether.core.command import Command
from aether.core.command_registry import CommandInfo, CommandRegistry
from aether.core.plugin import PluginBase, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.AIPlugin")

_AI_CONFIG_PATH = "config/ai.yaml"

_AI_DEFAULTS: dict = {
    "ai": {
        "enabled": True,
        "provider": "echo",
        "system_prompt": "You are Aether, the spatial AI operating system. Answer concisely.",
        "context": {
            "max_memory": 5,
            "include_vision": False,
            "max_memory_chars": 1500,
        },
        "intent": {
            "enabled": True,
            "classifier": "rule_based",
            "max_clarification_turns": 2,
        },
    },
}

_AI_COMMANDS = [
    CommandInfo(
        name="ai.chat",
        description="Send a message to the Aether assistant",
        category="ai",
        params_help="message=<text> [session_id=<id>]",
        examples=("ai.chat message=What do you see?",),
    ),
]


class AIPlugin(PluginBase):
    """Manages the AI chat service lifecycle and the ai.chat command."""

    name = "ai_plugin"

    def __init__(self) -> None:
        self._container: Optional[ServiceContainer] = None
        self._event_bus = None
        self._command_bus = None
        self._service: Optional[AIService] = None
        self._worker: Optional[AIWorker] = None
        self._ai_config: Optional[ConfigLoader] = None
        self._ai_config_path: str = _AI_CONFIG_PATH

    @property
    def ai_service(self) -> Optional[AIService]:
        """The functional AIService (UI facade)."""
        return self._service

    @property
    def worker(self) -> Optional[AIWorker]:
        """The background AI worker (Phase B1 async tick loop)."""
        return self._worker

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="AI",
            version="2.0",
            category="ai",
            commands=[c.name for c in _AI_COMMANDS],
            description="AI chat assistant + agent tool loop (provider pluggable)",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._event_bus = container.resolve("event_bus")
        self._command_bus = container.resolve("command_bus")

        self._ai_config = self._load_ai_config(container)
        if not self._ai_config.get("ai.enabled", True):
            logger.info("AIPlugin disabled via config (ai.enabled=false)")
            return

        system_prompt = self._ai_config.get("ai.system_prompt", "") or _AI_DEFAULTS["ai"]["system_prompt"]
        provider = self._create_provider(self._ai_config.get("ai.provider", "echo"))
        max_tool_rounds = int(self._ai_config.get("ai.max_tool_rounds", 5) or 5)

        context_cfg = self._ai_config.get("ai.context", {}) or {}
        max_memory = int(context_cfg.get("max_memory", 5) or 5)
        include_vision = bool(context_cfg.get("include_vision", False))
        max_memory_chars = int(context_cfg.get("max_memory_chars", 1500) or 1500)

        intent_cfg = self._ai_config.get("ai.intent", {}) or {}
        intent_enabled = bool(intent_cfg.get("enabled", True))
        max_clarification_turns = int(intent_cfg.get("max_clarification_turns", 2) or 2)

        memory_service = None
        if container.has("memory_service"):
            memory_service = container.resolve("memory_service")
        workspace_manager = None
        if container.has("workspace_manager"):
            workspace_manager = container.resolve("workspace_manager")
        panel_registry = None
        if container.has("panel_registry"):
            panel_registry = container.resolve("panel_registry")
        overlay_model = None
        if container.has("overlay_model"):
            overlay_model = container.resolve("overlay_model")

        memory_retriever = (
            DefaultMemoryRetriever(memory_service)
            if memory_service is not None
            else None
        )

        # Phase 3.3: IntentReasoner — a routing layer, not a second agent.
        # Enabled only when intent_enabled AND a rule-based classifier.
        intent_reasoner = None
        if intent_enabled:
            classifier = RuleBasedIntentClassifier()
            intent_reasoner = IntentReasoner(
                classifier=classifier,
                memory_retriever=memory_retriever,
                max_clarification_turns=max_clarification_turns,
            )

        context_engine = ContextEngine(
            system_prompt=system_prompt,
            workspace_manager=workspace_manager,
            panel_registry=panel_registry,
            memory_service=memory_service,
            overlay_model=overlay_model,
            include_vision=include_vision,
            max_memory=max_memory,
            max_memory_chars=max_memory_chars,
            memory_retriever=memory_retriever,
        )

        registry = ToolRegistry()
        executor = ToolExecutor(self._command_bus.dispatch_sync, registry=registry)

        self._service = AIService(
            provider=provider,
            event_bus=self._event_bus,
            memory_service=memory_service,
            context_engine=context_engine,
            tool_registry=registry,
            tool_executor=executor,
            max_tool_rounds=max_tool_rounds,
            max_memory=max_memory,
            max_memory_chars=max_memory_chars,
            memory_retriever=memory_retriever,
            intent_reasoner=intent_reasoner,
        )
        container.register_instance("ai_service", self._service)

        # Phase B1: background AI worker so ai.chat never blocks the 30 Hz
        # tick. submit() enqueues; AIService.chat runs on the worker thread
        # and results arrive via queued ai.* events on the main-thread flush.
        self._worker = AIWorker(self._service.chat, name="aether-ai-worker")
        self._worker.start()
        container.register_instance("ai_worker", self._worker)

        self._register_commands()

        # M1 Memory UX: when MemoryPlugin restores the last work session at
        # boot, inject it into the AI service so the next chat continues the
        # user's work without them re-explaining context.
        if self._event_bus is not None:
            self._event_bus.subscribe("memory.session.restored", self._on_session_restored)

        logger.info("AIPlugin initialized (provider=%s, tools=%d, intent=%s, worker=%s)",
                    provider.name, registry.count,
                    intent_reasoner is not None,
                    self._worker.running)

    def start(self) -> None:
        logger.info("AIPlugin started (provider=%s available=%s)",
                    self._service.provider_name if self._service else "?",
                    self._service.provider_available if self._service else False)

    def is_ready(self) -> bool:
        return self._service is not None

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
        if self._event_bus is not None:
            try:
                self._event_bus.unsubscribe("memory.session.restored", self._on_session_restored)
            except Exception:
                pass
        logger.info("AIPlugin stopped")

    # ── Config ─────────────────────────────────────────────────────

    def _load_ai_config(self, container: ServiceContainer) -> ConfigLoader:
        """Load config/ai.yaml, reusing ConfigLoader merge semantics.

        The container's base config is passed as `defaults` only when the
        ai.yaml file exists, so a missing file cannot cause the base config
        to be written out as ai.yaml. A custom path (tests) is honored.
        """
        base_data: dict = {}
        if container.has("config"):
            base = container.resolve("config")
            if hasattr(base, "data"):
                base_data = base.data

        if Path(self._ai_config_path).exists():
            loader = ConfigLoader(self._ai_config_path, defaults=base_data)
        else:
            loader = ConfigLoader(self._ai_config_path, defaults=_AI_DEFAULTS)
        loader.load()
        return loader

    def _create_provider(self, name: str) -> AIProvider:
        """Resolve the configured provider via the provider factory.

        An unknown or misconfigured provider raises ProviderError; it is
        logged loudly and falls back to echo so boot never hard-fails on an
        experimental config value.
        """
        try:
            return create_provider(name, self._ai_config.data if self._ai_config else {})
        except ProviderError as exc:
            logger.warning("AI provider '%s' unavailable (%s); using echo", name, exc)
            return create_provider("echo", {})

    # ── Command registration ───────────────────────────────────────

    def _register_commands(self) -> None:
        registry = None
        if self._container and self._container.has("command_registry"):
            registry = self._container.resolve("command_registry")
        else:
            registry = CommandRegistry()
            if self._container:
                registry.initialize(self._container)

        for cmd_info in _AI_COMMANDS:
            registry.register(cmd_info)

        if self._command_bus:
            self._command_bus.register_handler("ai.chat", self._handle_ai_chat)

    def _handle_ai_chat(self, command: Command) -> dict:
        """Route an ai.chat command through the AIService."""
        message = command.params.get("message", "").strip()
        if not message:
            return {"message": "Empty message"}
        if not self._service:
            return {"message": "AI service not initialized"}

        session_id = command.params.get("session_id", "default")
        result = self._service.chat(message, session_id=session_id)
        if result.state == AIState.ERROR:
            return {"message": "AI error", "error": "provider_failed"}
        return {"message": result.text}

    def _on_session_restored(self, event) -> None:
        """Inject the boot-restored work session into the AI service."""
        payload = event.payload if hasattr(event, "payload") else {}
        session = payload.get("session")
        if session and self._service is not None:
            self._service.inject_session_context(session)
