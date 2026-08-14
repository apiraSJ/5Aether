"""AI domain models — chat messages, state, context, and results.

Plain data holders shared by the AI provider layer, the AIService facade,
and any future UI / voice adapters. No I/O happens here.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover - runtime-safe string annotations
    from aether.ai.context import (
        MemoryContext,
        SystemContext,
        TaskContext,
        VisionContext,
        WorkspaceContext,
    )


class ChatRole(str, Enum):
    """Who produced a message in a conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class ToolCall:
    """A provider-neutral request to execute a tool."""

    id: str
    name: str
    arguments: Dict[str, Any]  # parsed JSON object, never a raw string

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "arguments": self.arguments}


@dataclass
class AIResponse:
    """A single provider response — text and/or tool calls."""

    text: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"  # "stop" | "tool_calls"


@dataclass
class ChatMessage:
    """A single message in a conversation."""

    role: ChatRole
    content: str
    created_at: float = field(default_factory=time.time)
    tool_calls: List[ToolCall] = field(default_factory=list)  # assistant only
    tool_call_id: Optional[str] = None  # tool result only

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


class AIState(str, Enum):
    """Lifecycle state of the assistant service."""

    IDLE = "idle"
    THINKING = "thinking"
    RESPONDING = "responding"
    ERROR = "error"


@dataclass
class AIContext:
    """Assembled conversation context handed to the provider.

    ``system`` / ``workspace`` / ``memory`` / ``task`` / ``vision`` are the
    Phase 3.1 domain contexts (see aether.ai.context). They default to None
    so Phase 1/2 callers constructing AIContext directly keep working.
    """

    system_prompt: str = ""
    messages: List[ChatMessage] = field(default_factory=list)
    memory_snippets: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    system: Optional["SystemContext"] = None
    workspace: Optional["WorkspaceContext"] = None
    memory: Optional["MemoryContext"] = None
    task: Optional["TaskContext"] = None
    vision: Optional["VisionContext"] = None


@dataclass
class AIResult:
    """Result of a single chat() call."""

    text: str
    session_id: str
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    provider: str = "echo"
    duration_ms: float = 0.0
    state: AIState = AIState.IDLE
    context: Optional[AIContext] = None
    tool_rounds: int = 0
