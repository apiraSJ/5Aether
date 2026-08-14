"""Integration tests for ContextEngine inside AIService + AIPlugin.

Covers the Phase 3.1 wiring:
  - AIService.chat() builds context via ContextEngine and reflects the
    actual tool round + tool names used this turn
  - Panel visibility and recent memory appear in the returned context
  - AIPlugin resolves workspace / memory / overlay sources from the container
  - Vision freeze: aether/ai/** has zero CV-stack imports
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from aether.ai.context import ContextEngine
from aether.ai.models import AIResponse, AIState, ChatMessage, ChatRole, ToolCall
from aether.ai.provider import AIProvider
from aether.ai.service import AIService
from aether.ai.tools import ToolExecutor, ToolRegistry
from aether.core.command import Command
from aether.core.command_bus import CommandBus
from aether.core.event_bus_v2 import EventBus
from aether.core.service_container import ServiceContainer
from aether.memory.memory_manager import MemoryManager
from aether.plugins.ai_plugin import AIPlugin
from aether.services.memory_service import MemoryService
from aether.ui.panel.panel_info import PanelInfo
from aether.ui.panel.panel_registry import PanelRegistry

AI_PACKAGE = Path(__file__).resolve().parents[1] / "aether" / "ai"


@pytest.fixture
def memory_service():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = MemoryManager(db_path=str(Path(tmpdir) / "memory.db"))
        manager.open()
        manager.seed_if_empty()
        yield MemoryService(manager, event_bus=EventBus(queued=False))
        manager.close()


class _ScriptedProvider(AIProvider):
    name = "scripted"

    def __init__(self, script) -> None:
        self._script = list(script)

    @property
    def available(self) -> bool:
        return True

    def respond(self, messages, tools):
        if not self._script:
            return AIResponse(text="done")
        return self._script.pop(0)


def _tool_round_response() -> AIResponse:
    return AIResponse(
        text="",
        tool_calls=[ToolCall(id="c1", name="system.ping", arguments={})],
        finish_reason="tool_calls",
    )


def _tool_executor() -> ToolExecutor:
    def dispatcher(command: Command):
        if command.name == "system.ping":
            return {"message": "pong"}
        raise RuntimeError("no handler registered")

    return ToolExecutor(dispatcher, registry=ToolRegistry())


def _registry() -> PanelRegistry:
    reg = PanelRegistry()
    reg.register(PanelInfo(id="memory", type="memory", visible=True))
    reg.register(PanelInfo(id="vision", type="vision", visible=False))
    reg.focus_panel("memory")
    return reg


def _service(provider: AIProvider, engine: ContextEngine) -> AIService:
    return AIService(
        provider=provider,
        context_engine=engine,
        tool_registry=ToolRegistry(),
        tool_executor=_tool_executor(),
    )


class TestAIServiceContextWiring:
    def test_ai_service_passes_tool_round_to_context(self):
        engine = ContextEngine()
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="pong done")])
        service = _service(provider, engine)
        result = service.chat("ping")
        assert result.state == AIState.IDLE
        assert result.tool_rounds == 1
        assert result.context is not None
        assert result.context.task is not None
        assert result.context.task.tool_round == 1
        assert result.context.task.recent_tools == ["system.ping"]

    def test_recent_tools_are_names_only(self):
        engine = ContextEngine()
        provider = _ScriptedProvider([_tool_round_response(), AIResponse(text="ok")])
        service = _service(provider, engine)
        result = service.chat("x")
        assert result.context.task.recent_tools == ["system.ping"]
        assert all(isinstance(t, str) for t in result.context.task.recent_tools)

    def test_no_tools_means_no_recent_tools(self):
        engine = ContextEngine()
        service = _service(_ScriptedProvider([AIResponse(text="hi")]), engine)
        result = service.chat("hello")
        assert result.context.task.tool_round == 0
        assert result.context.task.recent_tools == []

    def test_context_includes_visible_panels(self):
        engine = ContextEngine(panel_registry=_registry())
        service = _service(_ScriptedProvider([AIResponse(text="ok")]), engine)
        result = service.chat("what panels?")
        assert result.context.workspace is not None
        assert result.context.workspace.visible_panels == ["memory"]
        assert result.context.workspace.focused_panel == "memory"
        assert result.context.workspace.panel_count == 2

    def test_context_includes_recent_memory(self, memory_service):
        memory_service.add({"title": "Aether is the spatial AI OS", "content": "frozen context"})
        engine = ContextEngine(memory_service=memory_service)
        service = _service(_ScriptedProvider([AIResponse(text="ok")]), engine)
        result = service.chat("aether")
        assert result.context.memory is not None
        assert result.context.memory.relevant, "expected a search hit"
        titles = [r["title"] for r in result.context.memory.relevant]
        assert any("Aether is the spatial AI OS" in t for t in titles)

    def test_context_includes_memory_stats(self, memory_service):
        engine = ContextEngine(memory_service=memory_service)
        service = _service(_ScriptedProvider([AIResponse(text="ok")]), engine)
        result = service.chat("hi")
        assert result.context.memory.stats["total"] > 0

    def test_context_system_prompt_renderable(self, memory_service):
        from aether.ai.context import render_context_for_prompt

        engine = ContextEngine(panel_registry=_registry(), memory_service=memory_service)
        service = _service(_ScriptedProvider([AIResponse(text="ok")]), engine)
        result = service.chat("hi")
        rendered = render_context_for_prompt(result.context)
        assert "[System]" in rendered
        assert "[Workspace]" in rendered
        assert "[Memory]" in rendered
        assert "[Task]" in rendered


class TestAIPluginContextWiring:
    @pytest.fixture
    def container(self, memory_service):
        c = ServiceContainer()
        c.register_instance("event_bus", EventBus(queued=False))
        c.register_instance("command_bus", CommandBus())
        c.register_instance("panel_registry", _registry())
        c.register_instance("memory_service", memory_service)
        return c

    def test_plugin_resolves_context_sources(self, container):
        p = AIPlugin()
        p.initialize(container)
        engine = p._service._context_engine
        assert engine is not None
        assert engine._panel_registry is container.resolve("panel_registry")
        assert engine._memory_service is container.resolve("memory_service")
        assert engine._workspace_manager is None  # not registered → graceful

    def test_plugin_chat_includes_workspace_context(self, container):
        p = AIPlugin()
        p.initialize(container)
        cmd = Command(name="ai.chat", source="test", params={"message": "what do you see?"})
        result = p._handle_ai_chat(cmd)
        assert "what do you see?" in result["message"]

    def test_plugin_reads_context_config_defaults(self, container):
        p = AIPlugin()
        p.initialize(container)
        assert p._service._max_memory == 5


class TestVisionFreeze:
    FORBIDDEN = re.compile(r"\b(mediapipe|ultralytics|yolo|cv2|camera)\b", re.IGNORECASE)

    def test_ai_package_has_no_cv_imports(self):
        hits = []
        for path in sorted(AI_PACKAGE.rglob("*.py")):
            content = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(content.splitlines(), start=1):
                if self.FORBIDDEN.search(line):
                    hits.append(f"{path.relative_to(AI_PACKAGE.parent)}:{lineno}: {line.strip()}")
        assert hits == []

    def test_vision_off_service_builds_full_context(self, memory_service):
        engine = ContextEngine(
            panel_registry=_registry(),
            memory_service=memory_service,
            overlay_model=None,
            include_vision=False,
        )
        service = _service(_ScriptedProvider([AIResponse(text="ok")]), engine)
        result = service.chat("hi")
        assert result.context.vision is None
        assert result.context.system is not None
        assert result.context.workspace is not None
        assert result.context.memory is not None
        assert result.context.task is not None
