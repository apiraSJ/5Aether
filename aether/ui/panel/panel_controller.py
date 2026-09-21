"""PanelController — bridge between PanelWidget and backend services.

Architecture:
    PanelWidget → PanelController → PanelSession → PanelModel

Controller handles:
    - User actions (search, send message, toggle task)
    - Service calls (MemoryManager, LLM, TaskManager)
    - State updates (session.save_state)
    - Event subscription (EventBus)

Controller does NOT:
    - Know about QWidget (pure Python)
    - Handle rendering (Widget does that)
    - Manage window behavior (WorkspaceScene does that)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from aether.ui.panel.panel_session import PanelSession

logger = logging.getLogger("Aether.PanelController")


class PanelController(ABC):
    """Base controller for panel logic.

    Subclasses implement panel-specific behavior:
    - MemoryController: search, recall, pin, delete
    - ChatController: send message, streaming
    - TasksController: add, toggle, delete
    - DashboardController: metrics subscription
    """

    def __init__(self, session: PanelSession) -> None:
        self._session = session
        self._command_bus = None
        self._event_bus = None

    @property
    def session(self) -> PanelSession:
        return self._session

    @property
    def panel_id(self) -> str:
        return self._session.panel_id

    def wire_services(self, command_bus: Any = None, event_bus: Any = None) -> None:
        """Wire command/event buses. Called once during initialization."""
        self._command_bus = command_bus
        self._event_bus = event_bus
        self._on_wired()

    def _on_wired(self) -> None:
        """Override for post-wire setup (subscribe to events)."""
        pass

    @abstractmethod
    def handle_action(self, action: str, **kwargs) -> Any:
        """Handle a user action from the widget.

        Actions:
            search(query)     → search results
            send(text)        → send chat message
            toggle(task_id)   → toggle task completion
            close()           → close panel
            pin()             → pin/unpin panel
            minimize()        → minimize panel
            maximize()        → maximize/restore panel
            focus()           → panel gained focus
            blur()            → panel lost focus
        """
        ...

    @abstractmethod
    def get_state(self, key: str) -> Any:
        """Get a state value from the session."""
        ...

    @abstractmethod
    def set_state(self, key: str, value: Any) -> None:
        """Set a state value in the session."""
        ...

    def destroy(self) -> None:
        """Cleanup. Called when panel is being destroyed."""
        pass
