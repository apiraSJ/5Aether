"""Integration tests for Phase 3.3 Intent/Reasoning inside AIService.

Covers the end-to-end flows from the Phase 3.3 plan:
  - MEMORY_WRITE routes to retriever.remember() and confirms (no agent loop,
    no tool call).
  - MEMORY_RETRIEVAL pre-fetches memory, then runs the agent loop.
  - ACTION / QUESTION / UNKNOWN still pass through the existing agent loop.
  - CLARIFICATION returns a follow-up prompt.
  - Degradation: intent disabled or failing → exact pre-3.3 agent-loop behavior.
  - Vision/CV freeze: aether/ai/** has zero CV-stack imports.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from aether.ai.context import ContextEngine
from aether.ai.intent import IntentReasoner, RuleBasedIntentClassifier
from aether.ai.memory import DefaultMemoryRetriever
from aether.ai.models import AIResponse, AIState
from aether.ai.provider import AIProvider
from aether.ai.service import AIService
from aether.ai.tools import ToolExecutor, ToolRegistry
from aether.core.event_bus_v2 import EventBus
from aether.memory.memory_manager import MemoryManager
from aether.services.memory_service import MemoryService

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
        self.calls = 0

    @property
    def available(self) -> bool:
        return True

    def respond(self, messages, tools):
        self.calls += 1
        if not self._script:
            return AIResponse(text="done")
        return self._script.pop(0)


def _build_service(memory_service, text="ok", intent=True):
    retriever = DefaultMemoryRetriever(memory_service) if memory_service else None
    engine = ContextEngine(
        memory_service=memory_service,
        memory_retriever=retriever,
    )
    reasoner = None
    if intent:
        reasoner = IntentReasoner(
            classifier=RuleBasedIntentClassifier(),
            memory_retriever=retriever,
        )
    provider = _ScriptedProvider([AIResponse(text=text)])
    return AIService(
        provider=provider,
        context_engine=engine,
        tool_registry=ToolRegistry(),
        tool_executor=ToolExecutor(_dispatcher, registry=ToolRegistry()),
        memory_retriever=retriever,
        intent_reasoner=reasoner,
    ), provider


def _dispatcher(command):
    return {"message": "handled"}


class TestMemoryWriteFlow:
    def test_explicit_remember_stores_memory(self, memory_service):
        service, provider = _build_service(memory_service)
        result = service.chat("remember budget as 5000")
        # MEMORY_WRITE short-circuits: no LLM/tool round, correct state.
        assert result.state == AIState.IDLE
        assert provider.calls == 0
        assert "บันทึกเรียบร้อย" in result.text
        # The memory is now recallable.
        d = service._intent_reasoner.classifier.classify("budget")
        assert d is not None
        hits = memory_service.search("budget")
        assert hits, "expected the remembered fact to be searchable"

    def test_thai_remember(self, memory_service):
        service, _ = _build_service(memory_service)
        result = service.chat("จำไว้ว่าโปรเจกต์ Aether ใช้ PySide6")
        assert result.state == AIState.IDLE
        assert "บันทึกเรียบร้อย" in result.text
        assert memory_service.search("Aether")

    def test_general_statement_does_not_auto_save(self, memory_service):
        service, provider = _build_service(memory_service)
        result = service.chat("I like dark UI")
        # Not a memory write → agent loop runs (provider called).
        assert provider.calls == 1
        assert "บันทึก" not in result.text


class TestMemoryRetrievalFlow:
    def test_memory_retrieval_prefetches_then_agent_loop(self, memory_service):
        memory_service.add({"title": "Budget target", "summary": "budget is 5000"})
        service, provider = _build_service(memory_service)
        result = service.chat("what did I say about the budget?")
        # MEMORY_RETRIEVAL pre-fetches but STILL runs the agent loop.
        assert provider.calls == 1
        assert result.state == AIState.IDLE
        assert result.context is not None
        assert result.context.memory is not None
        titles = [r["title"] for r in result.context.memory.relevant]
        assert any("Budget" in t for t in titles)


class TestAgentLoopRouting:
    def test_action_routes_to_agent_loop(self):
        service, provider = _build_service(None)
        result = service.chat("open the memory panel")
        # ACTION always goes through the agent loop (never executed directly).
        assert provider.calls == 1
        assert result.state == AIState.IDLE

    def test_question_routes_to_agent_loop(self):
        service, provider = _build_service(None)
        result = service.chat("What is the capital of France?")
        assert provider.calls == 1
        assert result.state == AIState.IDLE

    def test_unknown_routes_to_agent_loop(self):
        service, provider = _build_service(None)
        result = service.chat("zzz qqq vvv")
        assert provider.calls == 1
        assert result.state == AIState.IDLE


class TestClarificationFlow:
    def test_clarification_returns_followup_no_agent_loop(self):
        service, provider = _build_service(None)
        result = service.chat("เอ่อ")
        assert provider.calls == 0
        assert result.state == AIState.IDLE
        assert isinstance(result.text, str) and result.text


class TestDegradation:
    def test_intent_disabled_runs_agent_loop(self, memory_service):
        service, provider = _build_service(memory_service, intent=False)
        result = service.chat("จำไว้ว่าโปรเจกต์ Aether ใช้ PySide6")
        assert provider.calls == 1  # agent loop ran, not a memory write
        assert result.state == AIState.IDLE

    def test_no_reasoner_is_pre_33(self, memory_service):
        # No intent_reasoner wired → everything goes to agent loop.
        retriever = DefaultMemoryRetriever(memory_service)
        engine = ContextEngine(memory_service=memory_service, memory_retriever=retriever)
        provider = _ScriptedProvider([AIResponse(text="ok")])
        service = AIService(provider=provider, context_engine=engine)
        assert service.intent_reasoner is None
        result = service.chat("remember x as y")
        assert provider.calls == 1


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

    def test_vision_still_none_with_intent(self, memory_service):
        service, _ = _build_service(memory_service)
        result = service.chat("hello")
        assert result.context.vision is None
