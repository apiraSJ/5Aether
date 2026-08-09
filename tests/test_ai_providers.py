"""Tests for AI providers — Echo, OpenAI (fake client), Local, and the factory."""

from __future__ import annotations

import pytest

from aether.ai.models import AIResponse, ChatMessage, ChatRole, ToolCall
from aether.ai.provider import EchoProvider, ProviderError
from aether.ai.providers import (
    EchoProvider as FactoryEcho,
    LocalProvider,
    OpenAIProvider,
    create_provider,
)
from aether.ai.tools import ToolDef


# ── Fake OpenAI client ──────────────────────────────────────────────────────


class _Fn:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _WireToolCall:
    def __init__(self, call_id: str, name: str, arguments: str) -> None:
        self.id = call_id
        self.function = _Fn(name, arguments)


class _WireMsg:
    def __init__(self, content=None, tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _WireChoice:
    def __init__(self, message, finish_reason: str) -> None:
        self.message = message
        self.finish_reason = finish_reason


class _WireResponse:
    def __init__(self, choices) -> None:
        self.choices = choices


class _FakeCompletions:
    def __init__(self, response=None, error=None) -> None:
        self._response = response
        self._error = error
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self._error is not None:
            raise self._error
        return self._response


class _FakeChat:
    def __init__(self, completions) -> None:
        self.completions = completions


class _FakeClient:
    def __init__(self, completions) -> None:
        self.chat = _FakeChat(completions)


def _provider_with(client) -> OpenAIProvider:
    return OpenAIProvider(model="gpt-4o-mini", client=client)


def _text_client(text: str = "hello"):
    resp = _WireResponse([_WireChoice(_WireMsg(text), "stop")])
    return _FakeClient(_FakeCompletions(resp))


# ── EchoProvider ────────────────────────────────────────────────────────────


class TestEchoProvider:
    def test_echo_available(self):
        assert EchoProvider().available is True

    def test_echo_returns_text_response(self):
        provider = EchoProvider()
        result = provider.respond(
            [ChatMessage(role=ChatRole.USER, content="ping")], []
        )
        assert isinstance(result, AIResponse)
        assert result.text == "[Echo] ping"
        assert result.tool_calls == []
        assert result.finish_reason == "stop"

    def test_echo_ignores_empty_tools(self):
        provider = EchoProvider()
        tools = [ToolDef(name="system.ping", description="ping", parameters={})]
        result = provider.respond(
            [ChatMessage(role=ChatRole.USER, content="hi")], tools
        )
        assert result.text == "[Echo] hi"
        assert result.tool_calls == []


# ── OpenAIProvider ──────────────────────────────────────────────────────────


class TestOpenAIProviderSuccess:
    def test_returns_text_response(self):
        provider = _provider_with(_text_client("hi there"))
        result = provider.respond([ChatMessage(role=ChatRole.USER, content="hi")], [])
        assert result.text == "hi there"
        assert result.tool_calls == []
        assert result.finish_reason == "stop"

    def test_parses_tool_calls(self):
        client = _FakeClient(_FakeCompletions(_WireResponse([
            _WireChoice(
                _WireMsg(
                    "calling",
                    [_WireToolCall("call_1", "system.ping", '{"ok": true}')],
                ),
                "tool_calls",
            )
        ])))
        provider = _provider_with(client)
        result = provider.respond(
            [ChatMessage(role=ChatRole.USER, content="ping")],
            [ToolDef(name="system.ping", description="ping", parameters={})],
        )
        assert result.finish_reason == "tool_calls"
        assert len(result.tool_calls) == 1
        call = result.tool_calls[0]
        assert call.id == "call_1"
        assert call.name == "system.ping"
        assert call.arguments == {"ok": True}

    def test_whitespace_content_stripped(self):
        provider = _provider_with(_text_client("  hi  "))
        result = provider.respond([], [])
        assert result.text == "hi"

    def test_passes_wire_tools_to_client(self):
        tool = ToolDef(
            name="memory.recall",
            description="recall",
            parameters={"type": "object", "properties": {"key": {"type": "string"}},
                        "required": ["key"]},
        )
        completions = _FakeCompletions(_WireResponse([_WireChoice(_WireMsg("ok"), "stop")]))
        provider = _provider_with(_FakeClient(completions))
        provider.respond([ChatMessage(role=ChatRole.USER, content="x")], [tool])
        assert completions.kwargs["tools"] == [{
            "type": "function",
            "function": {
                "name": "memory.recall",
                "description": "recall",
                "parameters": tool.parameters,
            },
        }]
        assert completions.kwargs["tool_choice"] == "auto"
        assert completions.kwargs["model"] == "gpt-4o-mini"


class TestOpenAIWireTranslation:
    def test_wire_tool_schema(self):
        tool = ToolDef(name="system.ping", description="ping", parameters={})
        wire = OpenAIProvider._to_wire_tool(tool)
        assert wire["type"] == "function"
        assert wire["function"]["name"] == "system.ping"
        assert wire["function"]["parameters"] == {}

    def test_wire_assistant_tool_calls(self):
        msg = ChatMessage(
            role=ChatRole.ASSISTANT,
            content="",
            tool_calls=[ToolCall(id="c1", name="system.ping", arguments={"ok": True})],
        )
        wire = OpenAIProvider._to_wire_message(msg)
        assert wire["tool_calls"][0]["id"] == "c1"
        assert wire["tool_calls"][0]["type"] == "function"
        assert wire["tool_calls"][0]["function"]["name"] == "system.ping"
        assert wire["tool_calls"][0]["function"]["arguments"] == '{"ok": true}'

    def test_wire_tool_message(self):
        msg = ChatMessage(role=ChatRole.TOOL, content="{}", tool_call_id="c1")
        wire = OpenAIProvider._to_wire_message(msg)
        assert wire["role"] == "tool"
        assert wire["tool_call_id"] == "c1"


class TestOpenAIProviderFailures:
    def test_api_failure_raises_provider_error(self):
        client = _FakeClient(_FakeCompletions(error=RuntimeError("connection reset")))
        provider = _provider_with(client)
        with pytest.raises(ProviderError):
            provider.respond([], [])

    def test_timeout_raises_provider_error(self):
        client = _FakeClient(_FakeCompletions(error=TimeoutError("Read timed out")))
        provider = _provider_with(client)
        with pytest.raises(ProviderError, match="Read timed out"):
            provider.respond([], [])

    def test_missing_choices_raises_provider_error(self):
        client = _FakeClient(_FakeCompletions(_WireResponse([])))
        provider = _provider_with(client)
        with pytest.raises(ProviderError, match="missing choices"):
            provider.respond([], [])

    def test_missing_message_raises_provider_error(self):
        client = _FakeClient(_FakeCompletions(_WireResponse([_WireChoice(None, "stop")])))
        provider = _provider_with(client)
        with pytest.raises(ProviderError, match="missing message"):
            provider.respond([], [])

    def test_invalid_tool_arguments_raises_provider_error(self):
        client = _FakeClient(_FakeCompletions(_WireResponse([
            _WireChoice(
                _WireMsg("x", [_WireToolCall("c1", "system.ping", "not-json")]),
                "tool_calls",
            )
        ])))
        provider = _provider_with(client)
        with pytest.raises(ProviderError, match="invalid tool arguments JSON"):
            provider.respond([], [])

    def test_tool_call_missing_name_raises_provider_error(self):
        client = _FakeClient(_FakeCompletions(_WireResponse([
            _WireChoice(_WireMsg("x", [_WireToolCall("c1", "", "{}")]), "tool_calls"),
        ])))
        provider = _provider_with(client)
        with pytest.raises(ProviderError, match="missing name"):
            provider.respond([], [])


class TestOpenAIProviderAvailability:
    def test_injected_client_is_available(self):
        provider = _provider_with(_FakeClient(_FakeCompletions()))
        assert provider.available is True

    def test_missing_api_key_is_unavailable(self):
        provider = OpenAIProvider()  # no key, no client
        assert provider.available is False

    def test_missing_package_is_unavailable(self, monkeypatch):
        real_import = __builtins__["__import__"]

        def fake_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("no openai installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", fake_import)
        provider = OpenAIProvider(api_key="test-key")
        assert provider.available is False

    def test_respond_without_client_raises_provider_error(self):
        provider = OpenAIProvider()  # no key
        with pytest.raises(ProviderError, match="unavailable"):
            provider.respond([], [])

    def test_from_config_reads_model_and_env_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        provider = OpenAIProvider.from_config({
            "model": "gpt-4o",
            "api_key_env": "OPENAI_API_KEY",
            "timeout": 10,
        })
        assert provider._model == "gpt-4o"
        assert provider._api_key == "sk-test"
        assert provider._timeout == 10

    def test_from_config_empty_uses_defaults(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        provider = OpenAIProvider.from_config(None)
        assert provider._model == "gpt-4o-mini"
        assert provider._api_key is None


# ── LocalProvider ───────────────────────────────────────────────────────────


class TestLocalProvider:
    def test_unavailable(self):
        assert LocalProvider().available is False

    def test_respond_raises_provider_error(self):
        with pytest.raises(ProviderError, match="not implemented"):
            LocalProvider().respond([], [])


# ── Factory ─────────────────────────────────────────────────────────────────


class TestProviderFactory:
    def test_echo(self):
        assert isinstance(create_provider("echo", {}), FactoryEcho)

    def test_openai(self):
        provider = create_provider("openai", {"openai": {"model": "gpt-4o-mini"}})
        assert isinstance(provider, OpenAIProvider)
        assert provider._model == "gpt-4o-mini"

    def test_local(self):
        assert isinstance(create_provider("local", {}), LocalProvider)

    def test_unknown_raises_provider_error(self):
        with pytest.raises(ProviderError, match="unknown provider"):
            create_provider("bogus", {})

    def test_default_is_echo(self):
        assert isinstance(create_provider(None, {}), FactoryEcho)
