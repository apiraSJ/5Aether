"""Tests for M1 Memory UX — AI-side work-session injection.

Covered: AIService.inject_session_context() feeding the next chat call,
AIPlugin subscribing to memory.session.restored, and the full boot chain
(memory plugin restores session → AIPlugin injects it into the AI service).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from aether.ai.models import AIResponse, ChatMessage, ChatRole
from aether.ai.provider import AIProvider
from aether.ai.service import AIService
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import Event, EventBus
from aether.core.service_container import ServiceContainer
from aether.plugins.ai_plugin import AIPlugin
from aether.plugins.memory_plugin import MemoryPlugin


class _RecordingProvider(AIProvider):
    """Captures the system messages the provider actually sees."""

    name = "recording"

    def __init__(self) -> None:
        self.system_messages: list[str] = []

    @property
    def available(self) -> bool:
        return True

    def respond(self, messages, tools=None):
        self.system_messages = [
            m.content for m in messages if m.role == ChatRole.SYSTEM
        ]
        user = [m for m in messages if m.role == ChatRole.USER]
        text = user[-1].content if user else ""
        return AIResponse(text=f"[Recording] {text}".strip(), finish_reason="stop")


@pytest.fixture
def container():
    c = ServiceContainer()
    c.register_instance("event_bus", EventBus(queued=False))
    c.register_instance("command_bus", CommandBus())
    return c


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "memory.db")


SESSION = {
    "id": "sess-1",
    "summary": "C3 cleanup in the Aether repo",
    "key_facts": ["Need to fix layout manager paths", "rewire theme manager seeds"],
    "updated_at": 123.0,
}


class TestAIServiceSessionInjection:
    def test_inject_sets_session_context(self):
        service = AIService()
        service.inject_session_context(SESSION)
        assert service._session_context is not None
        assert "C3 cleanup in the Aether repo" in service._session_context

    def test_inject_includes_key_facts(self):
        service = AIService()
        service.inject_session_context(SESSION)
        assert "Need to fix layout manager paths" in service._session_context
        assert "rewire theme manager seeds" in service._session_context

    def test_inject_none_is_noop(self):
        service = AIService()
        service.inject_session_context(None)
        assert service._session_context is None

    def test_inject_empty_summary_is_noop(self):
        service = AIService()
        service.inject_session_context({"summary": "  ", "key_facts": []})
        assert service._session_context is None

    def test_chat_includes_injected_session(self):
        provider = _RecordingProvider()
        service = AIService(provider=provider)
        service.inject_session_context(SESSION)
        service.chat("continue my work")
        assert any(
            "C3 cleanup in the Aether repo" in msg for msg in provider.system_messages
        )

    def test_chat_without_injection_has_single_system_message(self):
        provider = _RecordingProvider()
        service = AIService(provider=provider)
        service.chat("hello")
        assert len(provider.system_messages) == 1


class TestAIPluginSessionSubscription:
    def test_plugin_subscribes_to_session_restored(self, container):
        from aether.plugins.ai_plugin import AIPlugin as AP

        p = AP()
        p.initialize(container)
        event_bus = container.resolve("event_bus")
        assert event_bus.get_subscriber_count("memory.session.restored") >= 1
        p.stop()

    def test_plugin_injects_on_session_restored_event(self, container):
        from aether.plugins.ai_plugin import AIPlugin as AP

        p = AP()
        p.initialize(container)
        event_bus = container.resolve("event_bus")
        event_bus.publish(Event(
            type="memory.session.restored",
            payload={"session": SESSION},
            source="test",
        ))
        assert p._service._session_context is not None
        assert "C3 cleanup in the Aether repo" in p._service._session_context
        p.stop()

    def test_plugin_ignores_event_without_session(self, container):
        from aether.plugins.ai_plugin import AIPlugin as AP

        p = AP()
        p.initialize(container)
        container.resolve("event_bus").publish(Event(
            type="memory.session.restored", payload={}, source="test",
        ))
        assert p._service._session_context is None
        p.stop()

    def test_stop_unsubscribes(self, container):
        from aether.plugins.ai_plugin import AIPlugin as AP

        p = AP()
        p.initialize(container)
        event_bus = container.resolve("event_bus")
        p.stop()
        assert event_bus.get_subscriber_count("memory.session.restored") == 0


class TestBootChainIntegration:
    def test_memory_restore_feeds_ai_service(self, container, db_path):
        ai = AIPlugin()
        ai.initialize(container)

        mem = MemoryPlugin()
        mem._db_path = db_path
        mem.initialize(container)
        mem.start()
        mem._memory.create_session("Continue C3 work", ["rewire the seeds"])
        mem.stop()

        # Fresh memory plugin on the same DB restores the session; the already
        # initialized AIPlugin must pick it up automatically.
        mem2 = MemoryPlugin()
        mem2._db_path = db_path
        mem2.initialize(container)
        mem2.start()
        try:
            assert ai._service._session_context is not None
            assert "Continue C3 work" in ai._service._session_context
            assert "rewire the seeds" in ai._service._session_context
        finally:
            mem2.stop()
            ai.stop()