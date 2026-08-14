"""Unit tests for the ContextEngine — domain contexts, vision gate, rendering.

Covers the Phase 3.1 acceptance surface:
  - System / Workspace / Memory / Task / Vision domains build correctly
  - Vision is optional: None when no OverlayModel, populated when present
  - render_context_for_prompt emits compact JSON blocks per domain
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from aether import __version__
from aether.ai.context import (
    ContextEngine,
    render_context_for_prompt,
)
from aether.ai.models import ChatMessage, ChatRole
from aether.ui.panel.panel_info import PanelInfo
from aether.ui.panel.panel_registry import PanelRegistry


# ── Fakes ──────────────────────────────────────────────────────────────


class _FakeMemory:
    """MemoryService duck with search()/recent()/get_stats()."""

    def __init__(self) -> None:
        self._records = [{"type": "fact", "key": "foo", "value": "from recent"}]

    def search(self, query):
        return [{"type": "fact", "key": query, "value": "from search"}]

    def recent(self, limit):
        return self._records[:limit]

    def get_stats(self):
        return {"objects": 1, "fact_keys": 2, "total_facts": 3}


class _FakeScene:
    tracking = True
    object_count = 1
    hand_count = 2


class _FakeObject:
    id = "cup"
    name = "cup"
    box = [0, 0, 10, 20]
    confidence = 0.85


class _FakeCursor:
    visible = True
    x = 0.4
    y = 0.6
    state = type("S", (), {"value": "hover"})()


class _FakeGesture:
    name = "pinch"
    phase = type("P", (), {"value": "holding"})()
    confidence = 0.9


class _FakeOverlay:
    def __init__(self) -> None:
        self.scene = _FakeScene()
        self.objects = [_FakeObject()]
        self.cursor = _FakeCursor()
        self.gesture = _FakeGesture()


def _workspace_registry() -> PanelRegistry:
    reg = PanelRegistry()
    reg.register(PanelInfo(id="memory", type="memory", visible=True))
    reg.register(PanelInfo(id="vision", type="vision", visible=False))
    reg.focus_panel("memory")
    return reg


def _extract(rendered: str, header: str) -> dict:
    """Return the JSON block that follows the given section header."""
    lines = rendered.splitlines()
    for i, line in enumerate(lines):
        if line == header:
            return json.loads(lines[i + 1])
    raise AssertionError(f"section {header!r} missing from rendered context")


class TestSystemContext:
    def test_system_context_includes_time_version(self):
        ctx = ContextEngine().build([])
        assert ctx.system is not None
        assert ctx.system.aether_version == __version__
        parsed = datetime.strptime(ctx.system.current_time, "%Y-%m-%dT%H:%M:%S%z")
        assert parsed.tzinfo is not None
        assert "chat" in ctx.system.capabilities
        assert "tools" in ctx.system.capabilities

    def test_capabilities_reflect_injected_sources(self):
        engine = ContextEngine(
            memory_service=_FakeMemory(),
            panel_registry=_workspace_registry(),
            overlay_model=_FakeOverlay(),
            include_vision=True,
        )
        caps = engine.build([]).system.capabilities
        assert "memory" in caps
        assert "workspace" in caps
        assert "vision" in caps

    def test_vision_capability_absent_when_off(self):
        caps = ContextEngine(overlay_model=_FakeOverlay(), include_vision=False).build([]).system.capabilities
        assert "vision" not in caps


class TestWorkspaceContext:
    def test_workspace_context_reflects_visible_panels(self):
        engine = ContextEngine(panel_registry=_workspace_registry())
        ws = engine.build([]).workspace
        assert ws is not None
        assert ws.visible_panels == ["memory"]
        assert ws.focused_panel == "memory"
        assert ws.panel_count == 2

    def test_workspace_empty_when_no_sources(self):
        ws = ContextEngine().build([]).workspace
        assert ws is not None
        assert ws.visible_panels == []
        assert ws.focused_panel is None
        assert ws.panel_count == 0
        assert ws.workspace_id is None

    def test_workspace_reads_manager_state(self):
        class _Manager:
            current_workspace = "main"
            current_layout = "default"
        engine = ContextEngine(
            workspace_manager=_Manager(),
            panel_registry=_workspace_registry(),
        )
        ws = engine.build([]).workspace
        assert ws.workspace_id == "main"
        assert ws.layout_name == "default"


class TestMemoryContext:
    def test_memory_context_returns_search_results(self):
        engine = ContextEngine(memory_service=_FakeMemory())
        mem = engine.build([], query="foo", limit=5).memory
        assert mem is not None
        assert mem.relevant == [{"type": "fact", "key": "foo", "value": "from search"}]
        assert mem.stats == {"objects": 1, "fact_keys": 2, "total_facts": 3}

    def test_memory_context_empty_when_no_service(self):
        mem = ContextEngine().build([], query="foo", limit=5).memory
        assert mem is not None
        assert mem.relevant == []
        assert mem.stats == {}

    def test_memory_respects_limit(self):
        engine = ContextEngine(memory_service=_FakeMemory())
        mem = engine.build([], limit=0).memory
        assert len(mem.relevant) == 0


class TestTaskContext:
    def test_task_context_tracks_tool_round(self):
        ctx = ContextEngine().build(
            [],
            query="do it",
            tool_round=3,
            recent_tools=["system.ping", "memory.search"],
        )
        assert ctx.task is not None
        assert ctx.task.user_message == "do it"
        assert ctx.task.tool_round == 3
        assert ctx.task.recent_tools == ["system.ping", "memory.search"]

    def test_task_context_defaults(self):
        task = ContextEngine().build([]).task
        assert task is not None
        assert task.user_message == ""
        assert task.tool_round == 0
        assert task.recent_tools == []


class TestVisionContext:
    def test_vision_context_none_when_overlay_absent(self):
        engine = ContextEngine(include_vision=True, overlay_model=None)
        ctx = engine.build([])
        assert ctx.vision is None

    def test_vision_context_none_when_flag_off(self):
        engine = ContextEngine(include_vision=False, overlay_model=_FakeOverlay())
        assert engine.build([]).vision is None

    def test_vision_context_populated_when_present(self):
        engine = ContextEngine(include_vision=True, overlay_model=_FakeOverlay())
        vision = engine.build([]).vision
        assert vision is not None
        assert vision.tracking is True
        assert vision.object_count == 1
        assert vision.hand_count == 2
        assert vision.objects[0]["name"] == "cup"
        assert vision.objects[0]["confidence"] == 0.85
        assert vision.cursor == {"x": 0.4, "y": 0.6, "state": "hover"}
        assert vision.gesture == {"name": "pinch", "phase": "holding", "confidence": 0.9}


class TestRendering:
    def _full_context(self):
        return ContextEngine(
            panel_registry=_workspace_registry(),
            memory_service=_FakeMemory(),
            overlay_model=_FakeOverlay(),
            include_vision=True,
        ).build(
            [ChatMessage(role=ChatRole.USER, content="hi")],
            query="hi",
            limit=5,
            tool_round=2,
            recent_tools=["system.ping"],
        )

    def test_render_includes_all_domains(self):
        rendered = render_context_for_prompt(self._full_context())
        for header in ("[System]", "[Workspace]", "[Memory]", "[Task]", "[Vision]"):
            assert header in rendered
        block = _extract(rendered, "[System]")
        assert block["version"] == __version__
        assert _extract(rendered, "[Task]")["recent_tools"] == ["system.ping"]

    def test_render_omits_vision_when_off(self):
        engine = ContextEngine(overlay_model=_FakeOverlay(), include_vision=False)
        rendered = render_context_for_prompt(engine.build([]))
        assert "[Vision]" not in rendered
        assert "[System]" in rendered

    def test_render_is_compact_json(self):
        rendered = render_context_for_prompt(self._full_context())
        system_block = _extract(rendered, "[System]")
        assert '"version":' in json.dumps(system_block, separators=(",", ":"))
        # No whitespace between keys/colons — compact serialization.
        assert '{"time":"' in rendered

    def test_render_json_blocks_are_valid(self):
        rendered = render_context_for_prompt(self._full_context())
        for header in ("[System]", "[Workspace]", "[Memory]", "[Task]", "[Vision]"):
            block = _extract(rendered, header)
            assert isinstance(block, dict)

    def test_render_stays_within_token_budget(self):
        # ~2000-token budget ≈ ~8000 chars of compact JSON for typical state.
        rendered = render_context_for_prompt(self._full_context())
        assert len(rendered) < 8000


class TestVisionOffIdenticalBehavior:
    def test_vision_off_identical_behavior(self):
        registry = _workspace_registry()
        mem = _FakeMemory()
        messages = [ChatMessage(role=ChatRole.USER, content="hi")]
        off = ContextEngine(
            panel_registry=registry, memory_service=mem, overlay_model=None,
        ).build(messages, query="hi", limit=5, tool_round=1, recent_tools=["system.ping"])
        on = ContextEngine(
            panel_registry=registry, memory_service=mem,
            overlay_model=_FakeOverlay(), include_vision=True,
        ).build(messages, query="hi", limit=5, tool_round=1, recent_tools=["system.ping"])

        assert off.workspace == on.workspace
        assert off.memory == on.memory
        assert off.task == on.task
        assert off.system.capabilities == [c for c in on.system.capabilities if c != "vision"]
        assert off.vision is None
        assert on.vision is not None

    def test_engine_never_imports_cv_stack(self):
        forbidden = r"mediapipe|ultralytics|yolo|cv2|camera"
        content = Path(__file__).resolve().parents[1].joinpath("aether", "ai", "context.py")
        import re
        hits = [ln for ln, line in enumerate(content.read_text(encoding="utf-8").splitlines(), 1)
                if re.search(forbidden, line, re.IGNORECASE)]
        assert hits == []
