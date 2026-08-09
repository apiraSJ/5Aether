"""Streaming protocol for AI chat.

Phase 1.5 defines the internal streaming contract only — no EventBus
emission per token yet. UI subscription happens once the protocol is
stable (Phase 2).

A stream() generator yields a StreamEvent sequence:
    started → delta... → completed
    started → error
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

StreamEventType = Literal["started", "delta", "completed", "error"]


@dataclass
class StreamEvent:
    """One event in an AI response stream."""

    type: StreamEventType
    content: str = ""
    error: Optional[str] = None
    session_id: str = "default"

    @classmethod
    def started(cls, session_id: str = "default") -> "StreamEvent":
        return cls(type="started", session_id=session_id)

    @classmethod
    def delta(cls, content: str, session_id: str = "default") -> "StreamEvent":
        return cls(type="delta", content=content, session_id=session_id)

    @classmethod
    def completed(cls, content: str, session_id: str = "default") -> "StreamEvent":
        return cls(type="completed", content=content, session_id=session_id)

    @classmethod
    def error(cls, message: str, session_id: str = "default") -> "StreamEvent":
        return cls(type="error", error=message, session_id=session_id)
