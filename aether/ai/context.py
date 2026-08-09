"""ContextBuilder — assembles the AI conversation context.

Phase 1 scope:
  - Fixed system prompt (config-overridable) describing Aether.
  - Optional memory snippets pulled from MemoryService so the assistant can
    answer "what do you remember about X" without a live LLM.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from aether.ai.models import AIContext, ChatMessage

logger = logging.getLogger("Aether.AI.Context")

DEFAULT_SYSTEM_PROMPT = (
    "You are Aether, the spatial AI operating system. "
    "You can see the user's hands, remember facts and events, and "
    "control the workspace. Answer concisely."
)


class ContextBuilder:
    """Builds the system prompt + conversation + memory snippets for a chat."""

    def __init__(self, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> None:
        self._system_prompt = system_prompt

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def build(
        self,
        messages: List[ChatMessage],
        memory_service: Any = None,
        query: str = "",
        limit: int = 5,
        workspace: Optional[Dict[str, Any]] = None,
        tasks: Optional[Dict[str, Any]] = None,
    ) -> AIContext:
        """Assemble an AIContext.

        Args:
            messages: Conversation history (user + assistant turns).
            memory_service: Optional MemoryService used to gather relevant
                snippets. Skipped when None or unavailable.
            query: Current user message, used as the memory search query.
            limit: Max memory snippets to include.
            workspace: Optional workspace state snapshot (sections rendered
                into the system prompt). Skipped when None.
            tasks: Optional task state snapshot. Skipped when None.
        """
        snippets = self._gather_memory(memory_service, query, limit)
        return AIContext(
            system_prompt=self.system_text(workspace=workspace, tasks=tasks),
            messages=list(messages),
            memory_snippets=snippets,
            metadata={"memory_limit": limit},
        )

    def system_text(
        self,
        workspace: Optional[Dict[str, Any]] = None,
        tasks: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Compose the system prompt, appending optional context sections."""
        parts = [self._system_prompt]
        if workspace:
            parts.append(f"[Workspace]\n{self._format_section(workspace)}")
        if tasks:
            parts.append(f"[Tasks]\n{self._format_section(tasks)}")
        return "\n\n".join(parts)

    @staticmethod
    def _format_section(section: Dict[str, Any]) -> str:
        import json

        try:
            return json.dumps(section, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return str(section)

    def _gather_memory(
        self, memory_service: Any, query: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Pull recent or query-relevant memory records as plain dicts."""
        if memory_service is None:
            return []
        try:
            if query and query.strip():
                results = memory_service.search(query.strip())
                return list(results)[:limit]
            return list(memory_service.recent(limit))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Memory context gather failed: %s", exc)
            return []
