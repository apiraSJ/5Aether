"""Tests for the AIService agent loop — bounded tool rounds, transient tool
messages, structured tool failures, and vision independence."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from aether.ai.models import AIResponse, AIState, ChatMessage, ChatRole, ToolCall
from aether.ai.provider import AIProvider
from aether.ai.service import AIService
from aether.ai.tools import ToolExecutor, ToolRegistry
from aether.core.event_bus_v2 import EventBus
from aether.core.event_type import EventType

AI_PACKAGE = Path(__file__).resolve().parents[1] / "aether" / "ai"


class _ScriptedProvider(AIProvider):
    """Returns a scripted sequence of AIResponse objects."""

    name = "scripted"

    def __init__(self, script) -> None:
        self._script = list(script)
        self.respond_calls = []  # list of (messages, tools)

    @property
    def available(self) -> bool:
        return True

    def respond(self, messages, tools):
        self.respond_calls.append((list(messages), list(tools)))
        if not self._script:
            return AIResponse(text="done")
        return self._script.pop(0)


class _AlwaysToolProvider(AIProvider):
    name = "always-tool"

    @property
    def available(self) -> bool:
        return True

    def respond(self, messages, tools):
        return AIResponse(
            text="",
            tool_calls=[ToolCall(id="c1", name="system.ping", arguments={})],
            finish_reason="tool_calls",
        )


class _FailAfterToolProvider(AIProvider):
    name = "fail-after-tool"

    def __init__(self) -> None:
        self._calls = 0

    @property
    def available(self) -> bool:
        return True

    def respond(self, messages, tools):
        self._calls += 1
        if self._calls == 1:
            return AIResponse(
                text="",
                tool_calls=[ToolCall(id="c1", name="system.ping", arguments={})],
                finish_reason="tool_calls",
            )
        raise RuntimeError("boom on second call")


class _UnavailableProvider(AIProvider):
    name = "unavailable"

    def __init__(self) -> None:
        self.respond_calls = []

    @property
    def available(self) -> bool:
        return False

    def respond(self, messages, tools):
        self.respond_calls.append(1)
        raise AssertionError("respond must not be called")


def _tool_executor(recall_raises: bool = False) -> ToolExecutor:
    """Real ToolRegistry + ToolExecutor with a fake CommandBus dispatcher."""

    def dispatcher(command):
        if command.name == "system.ping":
            return {"message": "pong"}
        if command.name == "memory.recall":
            return {"key": command.params.get("key")}
        raise RuntimeError("no handler registered")

    return ToolExecutor(dispatcher, registry=ToolRegistry())


def _service(provider, event_bus=None, **kwargs) -> AIService:
    return AIService(
        provider=provider,
        event_bus=event_bus,
        tool_registry=ToolRegistry(),
        tool_executor=_tool_executor(),
        **kwargs,
    )


def _recall_service(provider, event_bus=None) -> AIService:
    return AIService(
        provider=provider,
        event_bus=event_bus,
        tool_registry=ToolRegistry(),
        tool_executor=_tool_executor(),
    )


def _collect_events(event_bus: EventBus, *event_types):
    """Subscribe to the given event types and return the captured list."""
    captured: list = []

    def _on_event(event):
        if event.type in event_types:
            captured.append(event)

    for event_type in event_types:
        event_bus.subscribe(event_type, _on_event)
    return captured


def _tool_round_response() -> AIResponse:
    return AIResponse(
        text="",
        tool_calls=[ToolCall(id="c1", name="system.ping", arguments={})],
        finish_reason="tool_calls",
    )


# ── Basic loop behaviour ────────────────────────────────────────────────────


class TestAgentLoopBasics:
    def test_text_only_response_no_tool_rounds(self):
        provider = _ScriptedProvider([AIResponse(text="hi")])
        service = _service(provider)
        result = service.chat("hello")
        assert result.state == AIState.IDLE
        assert result.text == "hi"
        assert result.tool_rounds == 0
        assert len(provider.respond_calls) == 1

    def test_single_tool_round(self):
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="pong done")])
        service = _service(provider)
        result = service.chat("ping")
        assert result.state == AIState.IDLE
        assert result.text == "pong done"
        assert result.tool_rounds == 1
        assert len(provider.respond_calls) == 2

    def test_multiple_tool_rounds(self):
        provider = _ScriptedProvider([
            _tool_round_response(),
            _tool_round_response(),
            AIResponse(text="final"),
        ])
        service = _service(provider)
        result = service.chat("go")
        assert result.text == "final"
        assert result.tool_rounds == 2
        assert len(provider.respond_calls) == 3

    def test_tool_rounds_counted_in_result(self):
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="ok")])
        service = _service(provider)
        result = service.chat("x")
        assert result.tool_rounds == 1


# ── Tool messages are transient ─────────────────────────────────────────────


class TestTransientToolMessages:
    def test_history_keeps_only_user_and_assistant(self):
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="done")])
        service = _service(provider)
        service.chat("ping", session_id="s1")
        roles = [m.role for m in service.history("s1")]
        assert roles == [ChatRole.USER, ChatRole.ASSISTANT]

    def test_provider_receives_tool_result_message(self):
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="done")])
        service = _service(provider)
        service.chat("ping")
        second_call_messages = provider.respond_calls[1][0]
        tool_msgs = [m for m in second_call_messages if m.role == ChatRole.TOOL]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].tool_call_id == "c1"
        assert '"success": true' in tool_msgs[0].content
        assert "pong" in tool_msgs[0].content

    def test_provider_receives_assistant_tool_call_message(self):
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="done")])
        service = _service(provider)
        service.chat("ping")
        second_call_messages = provider.respond_calls[1][0]
        assistant = [m for m in second_call_messages if m.role == ChatRole.ASSISTANT]
        assert len(assistant) == 1
        assert len(assistant[0].tool_calls) == 1
        assert assistant[0].tool_calls[0].name == "system.ping"


# ── Tool failures feed back to the LLM ──────────────────────────────────────


class TestToolFailures:
    def test_command_failure_fed_back_as_structured_result(self):
        dispatcher = lambda command: (_ for _ in ()).throw(RuntimeError("boom"))
        executor = ToolExecutor(dispatcher, registry=ToolRegistry())
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="ok")])
        service = AIService(
            provider=provider,
            tool_registry=ToolRegistry(),
            tool_executor=executor,
        )
        service.chat("x")
        tool_msgs = [m for m in provider.respond_calls[1][0] if m.role == ChatRole.TOOL]
        assert '"success": false' in tool_msgs[0].content
        assert '"error": "RuntimeError"' in tool_msgs[0].content

    def test_missing_required_argument_fed_back(self):
        provider = _ScriptedProvider([
            AIResponse(
                text="",
                tool_calls=[ToolCall(id="c2", name="memory.recall", arguments={})],
                finish_reason="tool_calls",
            ),
            AIResponse(text="needs key"),
        ])
        service = _recall_service(provider)
        service.chat("x")
        tool_msgs = [m for m in provider.respond_calls[1][0] if m.role == ChatRole.TOOL]
        assert '"success": false' in tool_msgs[0].content
        assert "missing required key 'key'" in tool_msgs[0].content

    def test_tools_passed_as_canonical_defs(self):
        registry = ToolRegistry()
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="ok")])
        service = AIService(
            provider=provider,
            tool_registry=registry,
            tool_executor=_tool_executor(),
        )
        service.chat("x")
        tools_passed = provider.respond_calls[0][1]
        assert tools_passed == registry.all()
        assert all(hasattr(t, "name") and hasattr(t, "parameters") for t in tools_passed)


# ── Bounding the loop ───────────────────────────────────────────────────────


class TestLoopBounds:
    def test_max_tool_rounds_exceeded_returns_error(self):
        service = _service(_AlwaysToolProvider(), max_tool_rounds=2)
        result = service.chat("x")
        assert result.state == AIState.ERROR
        assert result.text == ""

    def test_max_tool_rounds_exceeded_publishes_ai_error(self):
        event_bus = EventBus(queued=False)
        service = _service(_AlwaysToolProvider(), event_bus=event_bus, max_tool_rounds=1)
        service.chat("x")
        stats = event_bus.get_event_stats()
        assert stats["ai.error"]["published"] >= 1

    def test_max_tool_rounds_exceeded_does_not_crash(self):
        service = _service(_AlwaysToolProvider(), max_tool_rounds=3)
        assert service.chat("x")  # must not raise

    def test_provider_failure_after_tool_returns_error(self):
        service = _service(_FailAfterToolProvider())
        result = service.chat("x")
        assert result.state == AIState.ERROR
        assert result.text == ""


# ── Events ──────────────────────────────────────────────────────────────────


class TestToolEvents:
    def test_publishes_tool_started_and_completed(self):
        event_bus = EventBus(queued=False)
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="ok")])
        service = _service(provider, event_bus=event_bus)
        service.chat("ping")
        stats = event_bus.get_event_stats()
        assert stats["ai.tool.started"]["published"] >= 1
        assert stats["ai.tool.completed"]["published"] >= 1

    def test_completed_event_carries_success(self):
        event_bus = EventBus(queued=False)
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="ok")])
        service = _service(provider, event_bus=event_bus)
        completed = _collect_events(event_bus, EventType.AI_TOOL_COMPLETED)
        service.chat("ping")
        assert completed and completed[-1].payload["success"] is True
        assert completed[-1].payload["tool"] == "system.ping"


# ── Unavailable provider ────────────────────────────────────────────────────


class TestUnavailableProvider:
    def test_short_circuits_to_error(self):
        provider = _UnavailableProvider()
        service = AIService(provider=provider)
        result = service.chat("hello")
        assert result.state == AIState.ERROR
        assert result.text == ""
        assert provider.respond_calls == []

    def test_history_not_polluted(self):
        provider = _UnavailableProvider()
        service = AIService(provider=provider)
        service.chat("hello")
        assert service.history("default") == []

    def test_publishes_provider_unavailable_error(self):
        event_bus = EventBus(queued=False)
        service = AIService(provider=_UnavailableProvider(), event_bus=event_bus)
        errors = _collect_events(event_bus, EventType.AI_ERROR)
        service.chat("hello")
        stats = event_bus.get_event_stats()
        assert stats["ai.error"]["published"] >= 1
        assert errors[-1].payload["error"] == "provider_unavailable"


# ── Vision independence ─────────────────────────────────────────────────────


class TestVisionIndependence:
    FORBIDDEN = re.compile(r"\b(mediapipe|ultralytics|yolo|cv2|camera)\b", re.IGNORECASE)

    def test_ai_package_never_imports_cv_stack(self):
        hits = []
        for path in sorted(AI_PACKAGE.rglob("*.py")):
            content = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(content.splitlines(), start=1):
                if self.FORBIDDEN.search(line):
                    hits.append(f"{path.relative_to(AI_PACKAGE.parent)}:{lineno}: {line.strip()}")
        assert hits == []
