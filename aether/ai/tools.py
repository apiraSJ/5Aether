"""Canonical AI tools — ToolDef, ToolRegistry, and ToolExecutor.

Decisions (Phase 1.5):
  - ToolDef            = AI/domain definition (name, description, JSON Schema)
  - ToolRegistry       = registration + lookup, constrained by an explicit
                         whitelist. Never auto-exposes every CommandBus command.
  - ToolExecutor       = the Aether command integration boundary. It receives a
                         plain dispatcher callable (e.g. CommandBus.dispatch_sync);
                         tools.py never binds to the concrete CommandBus class.
  - Tool result        = structured {success, data, error} wrapper. Internal
                         exception details / stack traces never reach callers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional

from aether.core.command import Command

logger = logging.getLogger("Aether.AI.Tools")

# Explicit tool-safe command whitelist (Phase 1.5 approved set of 5).
DEFAULT_TOOL_SAFE_COMMANDS: frozenset[str] = frozenset({
    "ui.panel.toggle",
    "memory.recall",
    "memory.search",
    "system.ping",
    "system.info",
})


@dataclass(frozen=True)
class ToolDef:
    """Canonical definition of an AI-callable tool."""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass
class ToolResult:
    """Structured result of a tool execution — safe to hand to an LLM."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    tool: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"success": self.success, "data": self.data, "error": self.error}


_TOOL_SCHEMAS: Dict[str, ToolDef] = {
    "ui.panel.toggle": ToolDef(
        name="ui.panel.toggle",
        description="Toggle a workspace panel's visibility",
        parameters={
            "type": "object",
            "properties": {
                "panel_id": {"type": "string", "description": "Panel identifier to toggle"},
            },
            "required": ["panel_id"],
        },
    ),
    "memory.recall": ToolDef(
        name="memory.recall",
        description="Recall a memory record by key",
        parameters={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Memory key to recall"},
                "type": {"type": "string", "description": "Optional memory type filter"},
            },
            "required": ["key"],
        },
    ),
    "memory.search": ToolDef(
        name="memory.search",
        description="Full-text search memory",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    ),
    "system.ping": ToolDef(
        name="system.ping",
        description="Health check — confirm Aether is responsive",
        parameters={"type": "object", "properties": {}},
    ),
    "system.info": ToolDef(
        name="system.info",
        description="Show system runtime information",
        parameters={"type": "object", "properties": {}},
    ),
}


class ToolRegistry:
    """Registers + looks up canonical tools, constrained by an explicit whitelist."""

    def __init__(self, allowlist: Optional[Iterable[str]] = None) -> None:
        self._allowlist: frozenset[str] = (
            frozenset(allowlist) if allowlist is not None else DEFAULT_TOOL_SAFE_COMMANDS
        )
        self._tools: Dict[str, ToolDef] = {}
        for name, tool in _TOOL_SCHEMAS.items():
            if name in self._allowlist:
                self._tools[name] = tool

    @property
    def allowlist(self) -> frozenset[str]:
        return self._allowlist

    def register(self, tool: ToolDef) -> bool:
        """Register a tool. Refused (False) if its name is not whitelisted."""
        if tool.name not in self._allowlist:
            logger.warning("Refusing to register non-whitelisted tool: %s", tool.name)
            return False
        self._tools[tool.name] = tool
        return True

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def all(self) -> List[ToolDef]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def list_for_llm(self) -> List[Dict[str, Any]]:
        """Provider-agnostic tool list (name, description, parameters)."""
        return [t.to_dict() for t in self.all()]

    @property
    def count(self) -> int:
        return len(self._tools)


class ToolExecutor:
    """Executes whitelisted tools against the CommandBus boundary.

    Deliberately decoupled from CommandBus: it receives a plain dispatcher
    callable (e.g. command_bus.dispatch_sync). Results are wrapped in a
    structured ToolResult; exception type names only — never internals or
    stack traces.
    """

    def __init__(
        self,
        dispatcher: Callable[[Command], Any],
        registry: Optional[ToolRegistry] = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._registry = registry

    @property
    def registry(self) -> Optional[ToolRegistry]:
        return self._registry

    def execute(self, name: str, args: Optional[Dict[str, Any]] = None) -> ToolResult:
        name = (name or "").strip()
        if not name:
            return ToolResult(success=False, error="empty tool name", tool="")

        args = dict(args or {})

        if self._registry is not None:
            if name not in self._registry.allowlist:
                return ToolResult(
                    success=False, error=f"tool '{name}' is not tool-safe", tool=name,
                )
            tool = self._registry.get(name)
            if tool is None:
                return ToolResult(
                    success=False, error=f"tool '{name}' is not registered", tool=name,
                )
            missing = self._missing_required(tool, args)
            if missing:
                return ToolResult(
                    success=False,
                    error=f"invalid arguments: missing required key '{missing[0]}'",
                    tool=name,
                )

        command = Command(name=name, source="ai.tool", params=dict(args))
        try:
            result = self._dispatcher(command)
        except Exception as exc:
            logger.exception("Tool '%s' execution failed", name)
            return ToolResult(success=False, error=type(exc).__name__, tool=name)

        if result is None:
            return ToolResult(success=False, error="tool returned no result", tool=name)
        if isinstance(result, Command) and getattr(result, "error", None):
            return ToolResult(success=False, error=result.error, tool=name)

        return ToolResult(success=True, data=result, tool=name)

    @staticmethod
    def _missing_required(tool: ToolDef, args: Dict[str, Any]) -> List[str]:
        """Keys declared ``required`` in the tool's JSON Schema but absent."""
        parameters = tool.parameters or {}
        required = parameters.get("required") or []
        if not isinstance(required, list):
            return []
        return [k for k in required if k not in args]
