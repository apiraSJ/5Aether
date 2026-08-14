"""ContextEngine — assembles Aether's runtime state into a structured context.

Phase 1 scope:
  - Fixed system prompt (config-overridable) describing Aether.
  - Optional memory snippets pulled from MemoryService so the assistant can
    answer "what do you remember about X" without a live LLM.

Phase 3.1 scope:
  - Five context domains (System / Workspace / Memory / Task / Vision) each
    exposing only the fields an LLM needs for reasoning.
  - ``ContextEngine.build()`` aggregates the domains into a single
    ``AIContext``; ``render_context_for_prompt()`` renders it as compact JSON
    blocks prepended to the system prompt.
  - Vision is optional and frozen: ``aether/ai/**`` never imports the CV stack.
    ``VisionContext`` is produced only when ``include_vision=True`` AND an
    OverlayModel is injected.
"""

from __future__ import annotations

import json
import logging
import platform
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from aether import __version__
from aether.ai.models import AIContext, ChatMessage

logger = logging.getLogger("Aether.AI.Context")

DEFAULT_SYSTEM_PROMPT = (
    "You are Aether, the spatial AI operating system. "
    "You can see the user's hands, remember facts and events, and "
    "control the workspace. Answer concisely."
)


# ── Context domains ────────────────────────────────────────────────────


@dataclass
class SystemContext:
    """Static + environment information about the Aether runtime."""

    current_time: str  # ISO8601
    platform: str      # "Windows", "Linux", ...
    aether_version: str
    capabilities: List[str]


@dataclass
class WorkspaceContext:
    """Current workspace + panel layout state."""

    workspace_id: Optional[str]
    layout_name: Optional[str]
    visible_panels: List[str]
    focused_panel: Optional[str]
    panel_count: int


@dataclass
class MemoryContext:
    """Memory records relevant to the current turn + storage stats."""

    relevant: List[Dict[str, Any]]  # search(query) + recent()
    stats: Dict[str, int]           # objects, fact_keys, total_facts


@dataclass
class TaskContext:
    """Per-turn task state: the user message and tool activity."""

    user_message: str
    tool_round: int
    recent_tools: List[str]  # tool names only (no args) executed this turn


@dataclass
class VisionContext:
    """Snapshot of the vision overlay state (only when OverlayModel present)."""

    tracking: bool
    object_count: int
    hand_count: int
    objects: List[Dict[str, Any]]     # id, name, box, confidence
    cursor: Optional[Dict[str, Any]]  # x, y, state
    gesture: Optional[Dict[str, Any]]  # name, phase, confidence


# ── ContextEngine ──────────────────────────────────────────────────────


class ContextEngine:
    """Aggregates all context domains into a single AIContext.

    Every domain is defensive: a missing or failing source degrades to an
    empty value instead of raising, so the chat flow never depends on a
    service being registered.
    """

    def __init__(
        self,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        workspace_manager: Any = None,
        panel_registry: Any = None,
        memory_service: Any = None,
        overlay_model: Any = None,
        include_vision: bool = False,
        max_memory: int = 5,
    ) -> None:
        self._system_prompt = system_prompt
        self._workspace_manager = workspace_manager
        self._panel_registry = panel_registry
        self._memory_service = memory_service
        self._overlay_model = overlay_model
        self._include_vision = include_vision
        self._max_memory = max_memory

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def max_memory(self) -> int:
        return self._max_memory

    def build(
        self,
        messages: List[ChatMessage],
        query: str = "",
        limit: Optional[int] = None,
        tool_round: int = 0,
        recent_tools: Optional[List[str]] = None,
    ) -> AIContext:
        """Assemble full context for a single LLM call."""
        limit = limit if limit is not None else self._max_memory
        memory = self._build_memory(query, limit)
        return AIContext(
            system=self._build_system(),
            workspace=self._build_workspace(),
            memory=memory,
            task=self._build_task(query, tool_round, recent_tools),
            vision=self._build_vision(),
            system_prompt=self._system_prompt,
            messages=list(messages),
            memory_snippets=memory.relevant,
            metadata={"memory_limit": limit, "tool_round": tool_round},
        )

    # ── Private builders — one per domain ────────────────────────────

    def _build_system(self) -> SystemContext:
        return SystemContext(
            current_time=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            platform=platform.system() or sys.platform,
            aether_version=__version__,
            capabilities=self._capabilities(),
        )

    def _capabilities(self) -> List[str]:
        caps = ["chat", "tools"]
        if self._memory_service is not None:
            caps.append("memory")
        if self._workspace_manager is not None or self._panel_registry is not None:
            caps.append("workspace")
        if self._include_vision and self._overlay_model is not None:
            caps.append("vision")
        return caps

    def _build_workspace(self) -> WorkspaceContext:
        if self._workspace_manager is None and self._panel_registry is None:
            return WorkspaceContext(
                workspace_id=None, layout_name=None,
                visible_panels=[], focused_panel=None, panel_count=0,
            )

        workspace_id = _safe_attr(self._workspace_manager, "current_workspace")
        layout_name = _safe_attr(self._workspace_manager, "current_layout")

        registry = self._panel_registry
        if registry is None:
            registry = _safe_attr(self._workspace_manager, "_registry")

        visible_panels: List[str] = []
        focused_panel: Optional[str] = None
        panel_count = 0
        if registry is not None:
            try:
                visible_panels = [p.id for p in registry.list_visible()]
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Visible panel query failed: %s", exc)
            try:
                panel_count = int(registry.panel_count())
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Panel count query failed: %s", exc)
            try:
                focused = registry.get_focused()
                focused_panel = focused.id if focused else None
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Focused panel query failed: %s", exc)

        return WorkspaceContext(
            workspace_id=workspace_id,
            layout_name=layout_name,
            visible_panels=visible_panels,
            focused_panel=focused_panel,
            panel_count=panel_count,
        )

    def _build_memory(self, query: str, limit: int) -> MemoryContext:
        relevant = _gather_memory_records(self._memory_service, query, limit)
        stats: Dict[str, int] = {}
        if self._memory_service is not None:
            stats_fn = _safe_attr(self._memory_service, "get_stats") or _safe_attr(
                self._memory_service, "stats"
            )
            if stats_fn is not None:
                try:
                    stats = dict(stats_fn())
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("Memory stats failed: %s", exc)
        return MemoryContext(relevant=relevant, stats=stats)

    def _build_task(
        self,
        query: str,
        tool_round: int,
        recent_tools: Optional[List[str]],
    ) -> TaskContext:
        return TaskContext(
            user_message=query,
            tool_round=int(tool_round or 0),
            recent_tools=list(recent_tools or []),
        )

    def _build_vision(self) -> Optional[VisionContext]:
        """Vision gate: only when enabled AND an OverlayModel is injected."""
        if not self._include_vision or self._overlay_model is None:
            return None
        try:
            return self._build_vision_from_overlay()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Vision context build failed: %s", exc)
            return None

    def _build_vision_from_overlay(self) -> VisionContext:
        """Read the overlay model via duck typing — no UI/vision imports."""
        model = self._overlay_model
        scene = model.scene

        objects: List[Dict[str, Any]] = []
        for obj in model.objects:
            objects.append({
                "id": obj.id,
                "name": obj.name,
                "box": list(obj.box),
                "confidence": float(obj.confidence),
            })

        cursor: Optional[Dict[str, Any]] = None
        cursor_pos = model.cursor
        if cursor_pos.visible:
            cursor = {
                "x": float(cursor_pos.x),
                "y": float(cursor_pos.y),
                "state": getattr(cursor_pos.state, "value", str(cursor_pos.state)),
            }

        gesture: Optional[Dict[str, Any]] = None
        gesture_info = model.gesture
        if gesture_info.name and gesture_info.name != "Unknown":
            gesture = {
                "name": gesture_info.name,
                "phase": getattr(gesture_info.phase, "value", str(gesture_info.phase)),
                "confidence": float(gesture_info.confidence),
            }

        return VisionContext(
            tracking=bool(scene.tracking),
            object_count=int(scene.object_count),
            hand_count=int(scene.hand_count),
            objects=objects,
            cursor=cursor,
            gesture=gesture,
        )


def _safe_attr(obj: Any, name: str) -> Any:
    """Best-effort attribute read across source service variants."""
    if obj is None:
        return None
    try:
        return getattr(obj, name)
    except Exception:  # pragma: no cover - defensive
        return None


def _gather_memory_records(
    memory_service: Any, query: str, limit: int
) -> List[Dict[str, Any]]:
    """Best-effort memory retrieval across MemoryService variants.

    With a query: prefer ``search(query)``, fall back to
    ``recall_facts(first_token)``. Without: prefer ``recent(limit)``, fall
    back to ``list_objects()``. Never raises.
    """
    if memory_service is None:
        return []
    try:
        if query and query.strip():
            search = _safe_attr(memory_service, "search")
            if search is not None:
                return list(search(query.strip()))[:limit]
            recall = _safe_attr(memory_service, "recall_facts")
            if recall is not None:
                key = query.strip().split()[0]
                return list(recall(key))[:limit]
        recent = _safe_attr(memory_service, "recent")
        if recent is not None:
            return list(recent(limit))[:limit]
        objects = _safe_attr(memory_service, "list_objects")
        if objects is not None:
            return list(objects)[:limit]
        return []
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Memory context gather failed: %s", exc)
        return []


# ── Rendering for the LLM ──────────────────────────────────────────────


def render_context_for_prompt(context: AIContext) -> str:
    """Convert AIContext to compact JSON blocks prepended to system prompt.

    Each domain emits only fields useful for LLM reasoning. No exhaustive
    dumps. Missing domains (e.g. vision when OFF) are simply omitted.
    """
    parts = [context.system_prompt]
    if context.system is not None:
        parts.append(f"[System]\n{_json_dumps(_compact_system(context.system))}")
    if context.workspace is not None:
        parts.append(f"[Workspace]\n{_json_dumps(_compact_workspace(context.workspace))}")
    if context.memory is not None:
        parts.append(f"[Memory]\n{_json_dumps(_compact_memory(context.memory))}")
    if context.task is not None:
        parts.append(f"[Task]\n{_json_dumps(_compact_task(context.task))}")
    if context.vision is not None:
        parts.append(f"[Vision]\n{_json_dumps(_compact_vision(context.vision))}")
    return "\n\n".join(parts)


def _compact_system(ctx: SystemContext) -> Dict[str, Any]:
    return {
        "time": ctx.current_time,
        "platform": ctx.platform,
        "version": ctx.aether_version,
        "capabilities": ctx.capabilities,
    }


def _compact_workspace(ctx: WorkspaceContext) -> Dict[str, Any]:
    return {
        "workspace": ctx.workspace_id,
        "layout": ctx.layout_name,
        "visible_panels": ctx.visible_panels,
        "focused_panel": ctx.focused_panel,
        "panel_count": ctx.panel_count,
    }


def _compact_memory(ctx: MemoryContext) -> Dict[str, Any]:
    return {
        "relevant": ctx.relevant,
        "stats": ctx.stats,
    }


def _compact_task(ctx: TaskContext) -> Dict[str, Any]:
    return {
        "user_message": ctx.user_message,
        "tool_round": ctx.tool_round,
        "recent_tools": ctx.recent_tools,
    }


def _compact_vision(ctx: VisionContext) -> Dict[str, Any]:
    return {
        "tracking": ctx.tracking,
        "object_count": ctx.object_count,
        "hand_count": ctx.hand_count,
        "objects": ctx.objects,
        "cursor": ctx.cursor,
        "gesture": ctx.gesture,
    }


def _json_dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return str(obj)


# ── Backward-compatible shim (Phase 1/2 API) ───────────────────────────


class ContextBuilder:
    """Backward-compatible wrapper over ContextEngine (kept for callers of
    the Phase 1/2 API: build(messages, memory_service=..., workspace=...))."""

    def __init__(self, system_prompt: str = DEFAULT_SYSTEM_PROMPT, **engine_kwargs: Any) -> None:
        self._engine = ContextEngine(system_prompt=system_prompt, **engine_kwargs)

    @property
    def system_prompt(self) -> str:
        return self._engine.system_prompt

    def build(
        self,
        messages: List[ChatMessage],
        memory_service: Any = None,
        query: str = "",
        limit: int = 5,
        workspace: Optional[Dict[str, Any]] = None,
        tasks: Optional[Dict[str, Any]] = None,
    ) -> AIContext:
        """Assemble an AIContext (delegates to ContextEngine).

        ``memory_service`` is honored for Phase 1 callers that pass it per
        call; the engine's own injected memory service still wins when the
        caller passes None.
        """
        context = self._engine.build(messages, query=query, limit=limit)
        if memory_service is not None:
            snippets = self._gather_memory(memory_service, query, limit)
            context.memory_snippets = snippets
            if context.memory is not None:
                context.memory.relevant = list(snippets)
        if workspace or tasks:
            context.system_prompt = self.system_text(workspace=workspace, tasks=tasks)
        return context

    def system_text(
        self,
        workspace: Optional[Dict[str, Any]] = None,
        tasks: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Compose the system prompt, appending optional context sections."""
        parts = [self._engine.system_prompt]
        if workspace:
            parts.append(f"[Workspace]\n{self._format_section(workspace)}")
        if tasks:
            parts.append(f"[Tasks]\n{self._format_section(tasks)}")
        return "\n\n".join(parts)

    @staticmethod
    def _format_section(section: Dict[str, Any]) -> str:
        try:
            return json.dumps(section, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return str(section)

    @staticmethod
    def _gather_memory(
        memory_service: Any, query: str, limit: int
    ) -> List[Dict[str, Any]]:
        return _gather_memory_records(memory_service, query, limit)
