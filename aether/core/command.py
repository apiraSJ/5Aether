"""
Command — the standardized unit of intent flowing through Aether.

Per the ADR: every interaction, regardless of input source (gesture, voice,
keyboard, mouse, AI agent, automation, API), becomes one of these before
anything is executed. Nothing downstream of a Command needs to know or care
which input produced it.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class Command:
    """A single requested action, independent of its origin.

    Attributes:
        name:       Dotted command identifier, e.g. 'ui.toggle_home_menu'.
        source:     Where the command originated, e.g. 'gesture', 'keyboard',
                    'voice', 'ai_agent', 'api'.
        params:     Arbitrary parameters the handler needs to execute the command.
        context:    Optional context label the command was raised in
                    (e.g. the currently focused window/panel name).
        target:     Optional explicit target of the command
                    (e.g. an object id, a window name).
        id:         Unique id for this command instance, used for correlating
                    it with its CommandResult and in history/undo tracking.
        created_at: Unix timestamp of when the command was constructed.
        status:     Lifecycle state: PENDING → DISPATCHED → RUNNING → COMPLETED/FAILED.
        result:     Payload returned by the handler on success.
        error:      Error message string on failure.
    """

    name: str
    source: str
    params: Dict[str, Any] = field(default_factory=dict)
    context: Optional[str] = None
    target: Optional[str] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)
    status: str = "PENDING"
    result: Any = None
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.name, str):
            raise ValueError("Command.name must be a non-empty string.")
        if not self.source or not isinstance(self.source, str):
            raise ValueError("Command.source must be a non-empty string.")
