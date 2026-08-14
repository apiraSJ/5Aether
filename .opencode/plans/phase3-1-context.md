# Phase 3.1 — Context Engine

**Status:** **Approved for implementation** · Decisions locked
**Depends on:** Phase 2 (AI foundation, 787 tests passing)
**Blocked by:** None

---

## Objective

Build a **ContextEngine** that assembles Aether's runtime state into a structured prompt for the LLM — making the assistant "context-aware" before making it "smarter." Vision remains **optional** and **frozen**.

```
                    AIService
                       │
                 ContextEngine
                       │
       ┌───────────────┼───────────────┐
       │               │               │
 SystemContext    WorkspaceContext   MemoryContext
       │               │               │
       └───────────────┼───────────────┘
                       │
                 TaskContext
                       │
                 AIProvider
                       │
                      LLM
```

---

## Constraints (Non-Negotiable)

| Do Not Do | Reason |
|-----------|--------|
| ❌ LangGraph / CrewAI / smolagents / multi-agent frameworks | Aether's workflow is still simple; frameworks add abstraction debt |
| ❌ Change `AIProvider` contract | Stable since Phase 2; `respond(messages, tools) -> AIResponse` |
| ❌ Change Agent Loop | Bounded, tested, working (max 5 rounds, transient tool msgs) |
| ❌ Add autonomous behavior | Context ≠ agency; keep scope minimal |
| ❌ Require Vision / Camera / MediaPipe / YOLO | Context must work with Vision completely OFF |

---

## Data Sources (Already Exist)

| Domain | Source | Key Access Points |
|--------|--------|-------------------|
| **System** | `platform`, `sys`, `time`, `aether.__main__` | `current_time`, `os`, `aether_version`, `capabilities_list` |
| **Workspace** | `WorkspaceManager` + `PanelRegistry` | `current_workspace`, `current_layout`, `visible_panels()`, `focused_panel()` |
| **Memory** | `MemoryService` | `search(query)`, `recent(limit)`, `recall_facts(key)`, `list_objects()` |
| **Task** | `AIService` (per-turn) | `current_user_message`, `tool_round`, `tool_history` |
| **Vision (optional)** | `OverlayModel` (if `include_vision=true` AND Vision running) | `scene`, `objects[]`, `hands[]`, `cursor`, `gesture` |

---

## Architecture

### 3.1.1 New Types (`aether/ai/context.py`)

```python
@dataclass
class SystemContext:
    current_time: str           # ISO8601
    platform: str               # "Windows", "Linux", ...
    aether_version: str         # from __version__
    capabilities: List[str]     # ["chat", "tools", "memory", ...]

@dataclass
class WorkspaceContext:
    workspace_id: Optional[str]
    layout_name: Optional[str]
    visible_panels: List[str]
    focused_panel: Optional[str]
    panel_count: int

@dataclass
class MemoryContext:
    relevant: List[Dict[str, Any]]   # search(query) + recent()
    stats: Dict[str, int]            # objects, fact_keys, total_facts

@dataclass
class TaskContext:
    user_message: str
    tool_round: int
    recent_tools: List[str]          # tool names only (no args) executed this turn

@dataclass
class VisionContext:  # optional, only when OverlayModel present
    tracking: bool
    object_count: int
    hand_count: int
    objects: List[Dict[str, Any]]    # id, name, box, confidence
    cursor: Optional[Dict[str, Any]] # x, y, state
    gesture: Optional[Dict[str, Any]]# name, phase, confidence

@dataclass
class AIContext:
    system: SystemContext
    workspace: WorkspaceContext
    memory: MemoryContext
    task: TaskContext
    vision: Optional[VisionContext] = None
    # Existing fields preserved:
    system_prompt: str = ""
    messages: List[ChatMessage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 3.1.2 ContextEngine (`aether/ai/context.py`)

```python
class ContextEngine:
    """Aggregates all context domains into a single AIContext."""

    def __init__(
        self,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        workspace_manager: Any = None,
        panel_registry: Any = None,
        memory_service: Any = None,
        overlay_model: Any = None,          # optional — Vision
    ) -> None:
        self._system_prompt = system_prompt
        self._workspace_manager = workspace_manager
        self._panel_registry = panel_registry
        self._memory_service = memory_service
        self._overlay_model = overlay_model

    def build(
        self,
        messages: List[ChatMessage],
        query: str = "",
        limit: int = 5,
        tool_round: int = 0,
        recent_tools: Optional[List[str]] = None,
    ) -> AIContext:
        """Assemble full context for a single LLM call."""
        return AIContext(
            system=self._build_system(),
            workspace=self._build_workspace(),
            memory=self._build_memory(query, limit),
            task=self._build_task(query, tool_round, recent_tools),
            vision=self._build_vision(),
            system_prompt=self._system_prompt,
            messages=list(messages),
            metadata={"memory_limit": limit, "tool_round": tool_round},
        )

    # Private builders — one per domain
    def _build_system(self) -> SystemContext: ...
    def _build_workspace(self) -> WorkspaceContext: ...
    def _build_memory(self, query: str, limit: int) -> MemoryContext: ...
    def _build_task(self, query: str, tool_round: int, recent_tools: Optional[List[str]]) -> TaskContext: ...
    def _build_vision(self) -> Optional[VisionContext]: ...  # returns None if no overlay_model
```

### 3.1.3 Rendering for the LLM

```python
def render_context_for_prompt(context: AIContext) -> str:
    """Convert AIContext to compact JSON blocks prepended to system prompt.

    Each domain emits only fields useful for LLM reasoning. No exhaustive dumps.
    """
    parts = [context.system_prompt]
    parts.append(f"[System]\n{_json_dumps(_compact_system(context.system))}")
    parts.append(f"[Workspace]\n{_json_dumps(_compact_workspace(context.workspace))}")
    parts.append(f"[Memory]\n{_json_dumps(_compact_memory(context.memory))}")
    parts.append(f"[Task]\n{_json_dumps(_compact_task(context.task))}")
    if context.vision:
        parts.append(f"[Vision]\n{_json_dumps(_compact_vision(context.vision))}")
    return "\n\n".join(parts)
```

**Compact helpers** extract only reasoning-relevant fields (e.g., `TaskContext.recent_tools` = tool names only, no arguments). See implementation for exact projections.

---

## Integration Points

| Component | Change |
|-----------|--------|
| `AIService.chat()` | Pass `tool_round` + `recent_tools` (names only) to `ContextEngine.build()` |
| `AIPlugin.initialize()` | Resolve `WorkspaceManager`, `PanelRegistry`, optional `OverlayModel`; inject into `ContextEngine` |
| `config/ai.yaml` | Add `context: { max_memory: 5, include_vision: false }` |

**Vision gate semantics:**

```python
# ContextEngine._build_vision()
if self._include_vision and self._overlay_model is not None:
    return self._build_vision_from_overlay()
return None
```

- `include_vision = false` → `vision = null` (never reads OverlayModel)
- `include_vision = true` + `OverlayModel` present → `VisionContext` populated
- `include_vision = true` + no `OverlayModel` → `vision = null` (graceful)
- **Config never triggers Camera/CV startup**

---

## Tests

### Unit (`tests/test_context_engine.py`)

| Test | Assertion |
|------|-----------|
| `test_system_context_includes_time_version` | `system.current_time` parses, `aether_version` matches |
| `test_workspace_context_reflects_visible_panels` | `visible_panels` matches PanelRegistry |
| `test_memory_context_returns_search_results` | `search("foo")` results appear in `memory.relevant` |
| `test_task_context_tracks_tool_round` | `task.tool_round` increments per round |
| `test_vision_context_none_when_overlay_absent` | `vision is None` if no OverlayModel injected |
| `test_vision_context_populated_when_present` | `objects[]`, `hands[]`, `cursor` present |
| `test_render_includes_all_domains` | `render_context_for_prompt` contains all 5 sections |
| `test_vision_off_identical_behavior` | `ContextEngine(..., overlay_model=None)` produces identical `system/workspace/memory/task` as with Vision |

### Integration (`tests/test_ai_context_integration.py`)

| Test | Assertion |
|------|-----------|
| `test_ai_service_passes_tool_round_to_context` | Context includes correct round number |
| `test_context_includes_visible_panels` | Panel visibility changes reflected |
| `test_context_includes_recent_memory` | New fact appears in next turn's context |
| `test_vision_freeze_invariant` | All tests pass with `OverlayModel=None` (no CV imports) |

---

## Acceptance Criteria

1. **Vision OFF** — `ContextEngine(overlay_model=None)` builds complete System/Workspace/Memory/Task context; all 787 tests still pass.
2. **Vision optional** — If `OverlayModel` injected, `vision` section included; no CV imports in `aether/ai/**`.
3. **No regressions** — Full suite ≥ 787 passing.
4. **Context readable** — `render_context_for_prompt` produces valid JSON blocks per domain; total ≤ ~2000 tokens for typical state.
5. **Zero Agent Loop changes** — `AIService._run_agent_loop` untouched; only `chat()` call to ContextEngine changes.

---

## Files Touched

| File | Change |
|------|--------|
| `aether/ai/context.py` | New types + `ContextEngine` + `render_context_for_prompt` (extends existing `ContextBuilder`) |
| `aether/ai/service.py` | Pass `tool_round`, `recent_tools` to `build()`; no Agent Loop changes |
| `aether/plugins/ai_plugin.py` | Resolve + inject `WorkspaceManager`, `PanelRegistry`, optional `OverlayModel` |
| `config/ai.yaml` | Add `context:` section |
| `tests/test_context_engine.py` | New (unit) |
| `tests/test_ai_context_integration.py` | New (integration) |

---

## Rollout

1. Implement `ContextEngine` + types in `context.py` (backward-compat `ContextBuilder` shim)
2. Wire into `AIPlugin` + `AIService`
3. Add tests
4. Run full suite — verify 787+ pass, Vision freeze holds
5. Commit: `feat: Phase 3.1 Context Engine`
6. Tag: `v1.0.0-context-stable`

---

## Out of Scope (Future Phases)

- Phase 3.2: Memory-aware conversation (better retrieval, summarization, episodic linking)
- Phase 3.3: Intent/Reasoning (explicit reasoning steps, CoT prompting)
- Phase 3.4: Better Tools (file ops, web search, shell, code exec)
- Phase 3.5: Voice I/O (STT → Context → Agent → TTS)
- Phase 3.6: UI States (streaming deltas, thinking indicator, tool progress)
- Later: Vision re-integration as **optional adapter** into `ContextEngine`