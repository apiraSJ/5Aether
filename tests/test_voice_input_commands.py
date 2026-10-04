"""Tests for VoiceInputPlugin — commands, events, deterministic path (M2)."""

from __future__ import annotations

import sys

import pytest

from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.command_registry import CommandRegistry
from aether.core.event_bus_v2 import Event, EventBus
from aether.core.event_type import EventType
from aether.core.service_container import ServiceContainer
from aether.plugins.voice_input_plugin import VoiceInputPlugin
from aether.voice.stt import DeterministicSTTProvider


class _FakeConfig:
    """Minimal config stub exposing the dotted get() used by plugins."""

    def __init__(self, data):
        self._data = data

    def get(self, key_path, default=None):
        value = self._data
        for part in key_path.split("."):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value


def _container_for(data: dict) -> ServiceContainer:
    c = ServiceContainer()
    c.register_instance("event_bus", EventBus(queued=False))
    c.register_instance("command_bus", CommandBus())
    c.register_instance("config", _FakeConfig(data))
    registry = CommandRegistry()
    registry.initialize(c)
    return c


@pytest.fixture
def container():
    return _container_for({
        "voice": {
            "enabled": True,
            "provider": "deterministic",
            "scripts": ["เลือก component 2"],
        }
    })


@pytest.fixture
def plugin(container):
    p = VoiceInputPlugin()
    p.initialize(container)
    p.start()
    yield p
    try:
        p.stop()
    except Exception:
        pass


class TestLifecycle:
    def test_name(self):
        assert VoiceInputPlugin.name == "voice_input_plugin"

    def test_initialize_registers_services_and_commands(self, container):
        VoiceInputPlugin().initialize(container)
        assert container.has("voice_intent_parser")
        assert container.has("voice_stt_provider")
        registry = container.resolve("command_registry")
        for cmd in ("voice.listen", "voice.text", "voice.status"):
            assert registry.is_registered(cmd)

    def test_default_provider_is_deterministic(self, plugin):
        provider = plugin._provider
        assert isinstance(provider, DeterministicSTTProvider)
        assert provider.available
        assert provider.transcribe().text == "เลือก component 2"

    def test_metadata_lists_commands(self, container):
        p = VoiceInputPlugin()
        p.initialize(container)
        assert p.metadata.label == "Voice Input"
        assert "voice.listen" in p.metadata.commands

    def test_deterministic_path_does_not_import_optional_deps(self, plugin):
        import sys

        assert "sounddevice" not in sys.modules
        assert "vosk" not in sys.modules


class TestVoiceStatus:
    def test_status_reports_provider(self, plugin, container):
        command_bus = container.resolve("command_bus")
        result = command_bus.dispatch_sync(Command(name="voice.status", source="test"))
        assert result["enabled"] is True
        assert result["provider"] == "deterministic"
        assert result["available"] is True


class TestVoiceListen:
    def test_listen_dispatches_command_and_publishes_events(self, plugin, container):
        event_bus = container.resolve("event_bus")
        texts, intents, errors = [], [], []
        event_bus.subscribe(EventType.VOICE_TEXT_READY, lambda e: texts.append(e.payload))
        event_bus.subscribe(EventType.VOICE_INTENT_RESOLVED, lambda e: intents.append(e.payload))
        event_bus.subscribe(EventType.VOICE_ERROR, lambda e: errors.append(e.payload))

        command_bus = container.resolve("command_bus")
        seen = []
        command_bus.register_handler(
            "baseline.select",
            lambda c: seen.append((c.name, c.source, c.params)) or {"ok": True},
        )

        result = command_bus.dispatch_sync(Command(name="voice.listen", source="test", params={}))
        assert result["command_name"] == "baseline.select"
        command_bus.update()

        assert seen and seen[0] == ("baseline.select", "voice", {"component_id": "2"})
        assert texts[0]["text"] == "เลือก component 2"
        assert texts[0]["source"] == "deterministic"
        assert intents[0]["command"] == "baseline.select"
        assert intents[0]["params"]["component_id"] == "2"
        assert intents[0]["raw_input"] == "เลือก component 2"
        assert not errors

    def test_listen_degrades_when_provider_unavailable(self, plugin, container):
        plugin._provider = _UnavailableProvider()
        event_bus = container.resolve("event_bus")
        errors = []
        event_bus.subscribe(EventType.VOICE_ERROR, lambda e: errors.append(e.payload))
        command_bus = container.resolve("command_bus")
        result = command_bus.dispatch_sync(Command(name="voice.listen", source="test", params={}))
        assert "not available" in result["message"]
        assert errors and errors[0]["message"]

    def test_listen_degrades_when_deterministic_scripts_empty(self):
        c = _container_for({
            "voice": {"enabled": True, "provider": "deterministic", "scripts": []}
        })
        p = VoiceInputPlugin()
        p.initialize(c)
        command_bus = c.resolve("command_bus")
        result = command_bus.dispatch_sync(Command(name="voice.listen", source="test", params={}))
        assert "not available" in result["message"]


class TestVoiceText:
    def test_text_injects_and_dispatches(self, plugin, container):
        event_bus = container.resolve("event_bus")
        intents = []
        event_bus.subscribe(EventType.VOICE_INTENT_RESOLVED, lambda e: intents.append(e.payload))
        command_bus = container.resolve("command_bus")
        seen = []
        command_bus.register_handler(
            "baseline.status",
            lambda c: seen.append(c.name) or {"ok": True},
        )

        result = command_bus.dispatch_sync(
            Command(name="voice.text", source="test", params={"text": "สถานะ"})
        )
        assert result["command_name"] == "baseline.status"
        command_bus.update()
        assert seen == ["baseline.status"]
        assert intents[-1]["command"] == "baseline.status"

    def test_bare_capture_uses_last_selected_component(self, plugin, container):
        event_bus = container.resolve("event_bus")
        event_bus.publish(Event(
            type=EventType.BASELINE_SELECTED,
            payload={"component_id": "3"},
            source="test",
        ))
        command_bus = container.resolve("command_bus")
        seen = []
        command_bus.register_handler(
            "baseline.capture",
            lambda c: seen.append(c.params) or {"ok": True},
        )

        result = command_bus.dispatch_sync(
            Command(name="voice.text", source="test", params={"text": "ถ่ายภาพ"})
        )
        assert result["command_name"] == "baseline.capture"
        assert result["params"]["component_id"] == "3"
        command_bus.update()
        assert seen and seen[0] == {"component_id": "3"}

    def test_unknown_phrase_emits_voice_error(self, plugin, container):
        event_bus = container.resolve("event_bus")
        errors = []
        event_bus.subscribe(EventType.VOICE_ERROR, lambda e: errors.append(e.payload))
        command_bus = container.resolve("command_bus")

        result = command_bus.dispatch_sync(
            Command(name="voice.text", source="test", params={"text": "เปิดไฟในห้อง"})
        )
        assert "ไม่เข้าใจ" in result["message"]
        assert errors and "hint" in errors[0]
        command_bus.update()

    def test_empty_text_emits_error(self, plugin, container):
        event_bus = container.resolve("event_bus")
        errors = []
        event_bus.subscribe(EventType.VOICE_ERROR, lambda e: errors.append(e.payload))
        command_bus = container.resolve("command_bus")
        result = command_bus.dispatch_sync(
            Command(name="voice.text", source="test", params={"text": "  "})
        )
        assert "no text" in result["message"].lower()
        assert errors


class TestDisabledVoice:
    def test_disabled_plugin_returns_error(self):
        c = _container_for({
            "voice": {"enabled": False, "provider": "deterministic", "scripts": []}
        })
        p = VoiceInputPlugin()
        p.initialize(c)
        assert p._provider is None
        command_bus = c.resolve("command_bus")
        result = command_bus.dispatch_sync(Command(name="voice.listen", source="test", params={}))
        assert "disabled" in result["message"]

    def test_status_shows_disabled(self):
        c = _container_for({
            "voice": {"enabled": False, "provider": "deterministic", "scripts": []}
        })
        p = VoiceInputPlugin()
        p.initialize(c)
        command_bus = c.resolve("command_bus")
        result = command_bus.dispatch_sync(Command(name="voice.status", source="test"))
        assert result["enabled"] is False


class _UnavailableProvider:
    name = "mic"

    @property
    def available(self):
        return False

    def transcribe(self):
        return None