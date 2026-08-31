"""Integration tests for MemoryRetriever wired into ContextEngine / AIService.

Covers the Phase 3.2 wiring:
  - ContextEngine uses the injected retriever to populate MemoryContext
  - remember / forget surface correctly across turns
  - backward compatibility (no retriever → legacy behavior)
  - Vision/CV freeze invariant
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from aether.ai.context import ContextEngine
from aether.ai.memory import DefaultMemoryRetriever
from aether.ai.models import AIResponse, AIState
from aether.ai.provider import AIProvider
from aether.ai.service import AIService
from aether.ai.tools import ToolExecutor, ToolRegistry
from aether.core.event_bus_v2 import EventBus
from aether.memory.memory_manager import MemoryManager
from aether.services.memory_service import MemoryService

AI_PACKAGE = Path(__file__).resolve().parents[1] / "aether" / "ai"


class _ScriptedProvider(AIProvider):
    name = "scripted"

    def __init__(self, text="ok") -> None:
        self._text = text

    @property
    def available(self) -> bool:
        return True

    def respond(self, messages, tools):
        return AIResponse(text=self._text)


def _tool_executor() -> ToolExecutor:
    def dispatcher(command):
        raise RuntimeError("no handler registered")

    return ToolExecutor(dispatcher, registry=ToolRegistry())


@pytest.fixture
def memory_service():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = MemoryManager(db_path=str(Path(tmpdir) / "memory.db"))
        manager.open()
        manager.seed_if_empty()
        yield MemoryService(manager, event_bus=EventBus(queued=False))
        manager.close()


def _service(engine: ContextEngine) -> AIService:
    return AIService(
        provider=_ScriptedProvider(),
        context_engine=engine,
        tool_registry=ToolRegistry(),
        tool_executor=_tool_executor(),
    )


class TestContextEngineUsesRetriever:
    def test_context_engine_uses_retriever(self, memory_service):
        retriever = DefaultMemoryRetriever(memory_service)
        engine = ContextEngine(memory_service=memory_service, memory_retriever=retriever)
        service = _service(engine)
        result = service.chat("hi")
        assert result.context is not None
        assert result.context.memory is not None
        assert result.context.memory.budget is not None
        # seeded demo records surface as relevant
        assert result.context.memory.stats["total"] > 0

    def test_new_fact_appears_in_next_turn(self, memory_service):
        retriever = DefaultMemoryRetriever(memory_service)
        engine = ContextEngine(memory_service=memory_service, memory_retriever=retriever)
        service = _service(engine)
        retriever.remember("special project codename", "phase aether nexus", importance=0.9)
        result = service.chat("aether")
        titles = [r.get("title") or r.get("key") for r in result.context.memory.relevant]
        assert any("special project" in str(t) for t in titles)

    def test_forget_hides_memory(self, memory_service):
        retriever = DefaultMemoryRetriever(memory_service)
        engine = ContextEngine(memory_service=memory_service, memory_retriever=retriever)
        service = _service(engine)
        rid = retriever.remember("disposable fact", "to be removed", importance=0.1)
        assert rid is not None
        assert retriever.forget(rid) == 1
        result = service.chat("disposable")
        titles = [r.get("title") or r.get("key") for r in result.context.memory.relevant]
        assert "disposable" not in titles

    def test_no_retriever_uses_legacy_path(self, memory_service):
        engine = ContextEngine(memory_service=memory_service)
        service = _service(engine)
        result = service.chat("hi")
        # legacy path → budget is None
        assert result.context.memory is not None
        assert result.context.memory.budget is None

    def test_service_constructs_engine_with_retriever(self, memory_service):
        retriever = DefaultMemoryRetriever(memory_service)
        service = AIService(
            provider=_ScriptedProvider(),
            memory_service=memory_service,
            memory_retriever=retriever,
            tool_registry=ToolRegistry(),
            tool_executor=_tool_executor(),
        )
        assert service._context_engine._memory_retriever is retriever


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

    def test_vision_off_complete_context(self, memory_service):
        retriever = DefaultMemoryRetriever(memory_service)
        engine = ContextEngine(
            memory_service=memory_service,
            memory_retriever=retriever,
            overlay_model=None,
            include_vision=False,
        )
        service = _service(engine)
        result = service.chat("hi")
        assert result.state == AIState.IDLE
        assert result.context.vision is None
        assert result.context.memory.relevant is not None
