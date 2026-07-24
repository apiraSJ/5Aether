"""
CommandResult — the standardized outcome of executing a Command.

Per the ADR's "Problem 5" (Command has no standard output): every command
handler must return one of these instead of directly firing a notification,
opening a panel, or emitting an ad-hoc event. The ResultPipeline is the only
thing that interprets these fields and fans them out to notification,
history, layout, and the EventBus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CommandResult:
    """Standardized result returned by every Command handler.

    Attributes:
        success:        Whether the command completed successfully.
        command_id:     The id of the Command this result belongs to.
        command_name:   The name of the Command this result belongs to.
        message:        Human-readable summary, e.g. 'Object saved'.
        data:           Arbitrary structured data produced by the handler.
        error:          Error description when success is False.
        notification:   Notification style to show, or None for silent.
                        One of: 'toast', 'banner', 'popup', 'modal', None.
        history:        Whether this result should be recorded in command history.
        layout_action:  Optional layout instruction, e.g. 'focus_memory_panel'.
        undo:           Whether this command can be undone (used by later phases).
        duration_ms:    How long the handler took to execute, filled in by CommandBus.
    """

    success: bool
    command_id: str
    command_name: str
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    notification: Optional[str] = None
    history: bool = True
    layout_action: Optional[str] = None
    undo: bool = False
    duration_ms: float = 0.0

    @classmethod
    def ok(
        cls,
        command_id: str,
        command_name: str,
        message: str = "",
        data: Optional[Dict[str, Any]] = None,
        notification: Optional[str] = None,
        layout_action: Optional[str] = None,
        undo: bool = False,
    ) -> "CommandResult":
        """Build a successful CommandResult."""
        return cls(
            success=True,
            command_id=command_id,
            command_name=command_name,
            message=message,
            data=data or {},
            notification=notification,
            layout_action=layout_action,
            undo=undo,
        )

    @classmethod
    def fail(
        cls,
        command_id: str,
        command_name: str,
        error: str,
        message: str = "",
        notification: Optional[str] = None,
    ) -> "CommandResult":
        """Build a failed CommandResult."""
        return cls(
            success=False,
            command_id=command_id,
            command_name=command_name,
            message=message or "Command failed.",
            error=error,
            notification=notification,
        )
