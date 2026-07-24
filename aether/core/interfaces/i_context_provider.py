"""IContextProvider — contract for context snapshots.

Reasoning should NOT read window handles, mouse coordinates, or raw
perception data. It should receive a ContextSnapshot — the distilled
"state of mind" that matters for decision-making.

Example:
    provider = DesktopContextProvider(win32gui, psutil)
    ctx = provider.snapshot()
    # ContextSnapshot(
    #     interaction_mode=DEVELOPER,
    #     active_window="aether/core/interfaces/i_memory_repository.py - VS Code",
    #     focused_object=None,
    #     session_id="session_abc123",
    # )
    answer = reasoning.where_is("laptop", context=ctx)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from aether.domain.context_snapshot import ContextSnapshot, InteractionMode


class IContextProvider(ABC):
    """Provides context snapshots for reasoning."""

    @abstractmethod
    def snapshot(self) -> ContextSnapshot:
        """Return immutable context snapshot.

        Should be fast (< 10ms) and non-blocking.
        Caches results internally; refreshes on demand.
        """
        ...

    @abstractmethod
    def current_mode(self) -> InteractionMode:
        """Return current interaction mode."""
        ...

    @abstractmethod
    def active_target(self) -> Optional[str]:
        """Return the currently focused/selected object name, or None."""
        ...

    @abstractmethod
    def session_id(self) -> str:
        """Return current session identifier."""
        ...

    def invalidate(self) -> None:
        """Force next snapshot() to refresh from source.

        Default implementation does nothing (stateless providers).
        Override if provider caches state.
        """
        pass
