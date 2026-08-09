"""Tests for AIPlugin — lifecycle, ai.chat command, EventBus integration."""

from __future__ import annotations

import pytest

from aether.ai.models import AIState
from aether.ai.provider import AIProvider, EchoProvider
from aether.ai.service import AIService
from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import EventBus
from aether.core.service_container import ServiceContainer
from aether.plugins.ai_plugin import AIPlugin


class _FailingProvider(AIProvider):
    name = "failing"

    @property
    def available(self) -> bool:
        # True so chat() takes the respond() exception path (not the
        # provider_unavailable short-circuit).
        return True

    def respond(self, messages, tools=None):
        raise RuntimeError("boom")


@pytest.fixture
def container():
    c = ServiceContainer()
    c.register_instance("event_bus", EventBus(queued=False))
    c.register_instance("command_bus", CommandBus())
    return c


@pytest.fixture
def plugin(container):
    p = AIPlugin()
    p.initialize(container)
    yield p
    try:
        p.stop()
    except Exception:
        pass


class TestAIPluginLifecycle:
    def test_initialize_creates_service(self, container):
        p = AIPlugin()
        p.initialize(container)
        assert p._service is not None
        assert isinstance(p._service, AIService)
        assert container.has("ai_service")

    def test_service_uses_echo_provider(self, container):
        p = AIPlugin()
        p.initialize(container)
        assert p._service.provider_name == "echo"
        assert p._service.provider_available is True

    def test_is_ready_after_initialize(self, container):
        p = AIPlugin()
        p.initialize(container)
        assert p.is_ready()

    def test_metadata(self, container):
        p = AIPlugin()
        m = p.metadata
        assert m.label == "AI"
        assert "ai.chat" in m.commands

    def test_name(self):
        assert AIPlugin.name == "ai_plugin"


class TestAIPluginCommands:
    def test_handler_registration(self, container):
        p = AIPlugin()
        p.initialize(container)
        cmd_bus = container.resolve("command_bus")
        assert cmd_bus.is_registered("ai.chat")

    def test_ai_chat_empty_message(self, plugin):
        cmd = Command(name="ai.chat", source="test", params={"message": ""})
        result = plugin._handle_ai_chat(cmd)
        assert "Empty message" in result["message"]

    def test_ai_chat_echo(self, plugin):
        cmd = Command(name="ai.chat", source="test", params={"message": "hello aether"})
        result = plugin._handle_ai_chat(cmd)
        assert "hello aether" in result["message"]

    def test_ai_chat_via_command_bus(self, plugin, container):
        cmd_bus = container.resolve("command_bus")
        result = cmd_bus.dispatch_sync(Command(
            name="ai.chat", source="test", params={"message": "ping"},
        ))
        assert "ping" in result["message"]

    def test_ai_chat_tracks_session_history(self, plugin, container):
        cmd_bus = container.resolve("command_bus")
        cmd_bus.dispatch_sync(Command(
            name="ai.chat", source="test", params={"message": "first", "session_id": "s1"},
        ))
        cmd_bus.dispatch_sync(Command(
            name="ai.chat", source="test", params={"message": "second", "session_id": "s1"},
        ))
        history = plugin._service.history("s1")
        assert len(history) == 4  # user, assistant, user, assistant
        assert history[0].content == "first"
        assert history[2].content == "second"

    def test_ai_chat_sessions_are_isolated(self, plugin, container):
        cmd_bus = container.resolve("command_bus")
        cmd_bus.dispatch_sync(Command(
            name="ai.chat", source="test", params={"message": "only a"},
        ))
        history = plugin._service.history("default")
        assert len(history) == 2
        assert plugin._service.history("other") == []


class TestAIPluginEvents:
    def test_chat_publishes_ai_events(self, container):
        p = AIPlugin()
        p.initialize(container)
        event_bus = container.resolve("event_bus")
        p._service.chat("hello")
        stats = event_bus.get_event_stats()
        assert stats["ai.thinking.started"]["published"] >= 1
        assert stats["ai.thinking.completed"]["published"] >= 1
        assert stats["ai.response.ready"]["published"] >= 1

    def test_chat_publishes_state_changes(self, container):
        p = AIPlugin()
        p.initialize(container)
        event_bus = container.resolve("event_bus")
        p._service.chat("hello")
        stats = event_bus.get_event_stats()
        assert stats["ai.state.changed"]["published"] >= 3  # thinking, responding, idle

    def test_state_returns_to_idle(self, container):
        p = AIPlugin()
        p.initialize(container)
        p._service.chat("hello")
        assert p._service.state == AIState.IDLE


class TestAIService:
    def test_constructor_defaults_to_echo(self):
        service = AIService()
        assert isinstance(service._provider, EchoProvider)
        assert service.state == AIState.IDLE

    def test_empty_message_returns_error(self):
        service = AIService()
        result = service.chat("   ")
        assert result.state == AIState.ERROR
        assert result.text == ""

    def test_stream_single_chunk(self):
        service = AIService()
        events = list(service.stream("hello stream"))
        assert [e.type for e in events] == ["started", "delta", "completed"]
        assert events[1].content == "[Echo] hello stream"
        assert events[2].content == "[Echo] hello stream"

    def test_stream_error_event(self):
        service = AIService(provider=_FailingProvider())
        events = list(service.stream("hello"))
        assert [e.type for e in events] == ["started", "error"]
        assert events[1].error is not None

    def test_reset_session_clears_history(self):
        service = AIService()
        service.chat("hello")
        assert len(service.history()) == 2
        service.reset_session()
        assert service.history() == []

    def test_execute_tool_not_configured(self):
        service = AIService()
        result = service.execute_tool("system.ping")
        assert result.success is False
        assert "not configured" in result.error


class TestProviderFailure:
    def test_provider_exception_returns_error_state(self):
        service = AIService(provider=_FailingProvider())
        result = service.chat("hello")
        assert result.state == AIState.ERROR
        assert result.text == ""

    def test_provider_exception_does_not_crash(self):
        service = AIService(provider=_FailingProvider())
        result = service.chat("hello")  # must not raise
        assert result.state == AIState.ERROR

    def test_provider_exception_publishes_ai_error(self):
        event_bus = EventBus(queued=False)
        service = AIService(provider=_FailingProvider(), event_bus=event_bus)
        service.chat("hello")
        stats = event_bus.get_event_stats()
        assert stats["ai.error"]["published"] >= 1

    def test_provider_exception_returns_state_to_error(self):
        service = AIService(provider=_FailingProvider())
        service.chat("hello")
        assert service.state == AIState.ERROR

    def test_ai_chat_handler_provider_failure(self, container):
        p = AIPlugin()
        p.initialize(container)
        p._service = AIService(provider=_FailingProvider(), event_bus=container.resolve("event_bus"))
        cmd = Command(name="ai.chat", source="test", params={"message": "hello"})
        result = p._handle_ai_chat(cmd)
        assert "AI error" in result["message"]


class TestAIPluginTools:
    def test_plugin_wires_tool_registry(self, plugin):
        assert plugin._service.tool_registry is not None
        assert plugin._service.tool_registry.count == 5

    def test_plugin_tool_execution_via_command_bus(self, plugin, container):
        container.resolve("command_bus").register_handler(
            "system.ping", lambda c: {"message": "pong"},
        )
        result = plugin._service.execute_tool("system.ping")
        assert result.success is True
        assert result.data["message"] == "pong"

    def test_plugin_tool_whitelist_blocks_internal_command(self, plugin):
        result = plugin._service.execute_tool("system.shutdown")
        assert result.success is False
        assert "not tool-safe" in result.error


class TestAIPluginConfig:
    def test_loads_ai_yaml_config(self, container):
        p = AIPlugin()
        p.initialize(container)
        assert p._ai_config is not None
        assert p._ai_config.get("ai.enabled") is True
        assert p._ai_config.get("ai.provider") == "echo"

    def test_disabled_plugin_skips_service(self, container, tmp_path):
        ai_file = tmp_path / "ai.yaml"
        ai_file.write_text("ai:\n  enabled: false\n", encoding="utf-8")
        p = AIPlugin()
        p._ai_config_path = str(ai_file)
        p.initialize(container)
        assert p._service is None
        assert not container.has("ai_service")

    def test_disabled_plugin_does_not_register_handler(self, container, tmp_path):
        ai_file = tmp_path / "ai.yaml"
        ai_file.write_text("ai:\n  enabled: false\n", encoding="utf-8")
        p = AIPlugin()
        p._ai_config_path = str(ai_file)
        p.initialize(container)
        assert container.resolve("command_bus").is_registered("ai.chat") is False
