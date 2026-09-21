"""SystemPanel — displays system status, uptime, and diagnostics.

Stateless renderer — reads from SystemSnapshot.
Shows: uptime, platform, command count, event queue, CPU, memory.

Panel type: 'system'
Z-index: 5
"""

from __future__ import annotations

import platform
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from aether.ui.panel.abstract_panel import AbstractPanel


@dataclass
class SystemSnapshot:
    """Current system state for display."""

    uptime: float = 0.0
    platform: str = ""
    python_version: str = ""
    commands_registered: int = 0
    commands_processed: int = 0
    event_queue_depth: int = 0
    plugins_loaded: int = 0
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "uptime": self.uptime,
            "platform": self.platform,
            "python_version": self.python_version,
            "commands_registered": self.commands_registered,
            "commands_processed": self.commands_processed,
            "event_queue_depth": self.event_queue_depth,
            "plugins_loaded": self.plugins_loaded,
            "cpu_percent": self.cpu_percent,
            "memory_mb": self.memory_mb,
            "errors": self.errors,
        }


class SystemPanel(AbstractPanel):
    """Displays system status and diagnostics.

    Stateless renderer — reads from SystemSnapshot.
    Updated by SystemCommandPlugin or Application tick.
    """

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 820,
        height: int = 200,
    ) -> None:
        super().__init__(
            panel_id="system",
            x=x,
            y=y,
            width=width,
            height=height,
            z_index=5,
        )
        self._snapshot = SystemSnapshot(
            platform=platform.system(),
            python_version=platform.python_version(),
        )
        self._boot_time = time.time()

    # ── Data model ─────────────────────────────────────────────────

    def update_snapshot(self, snapshot: SystemSnapshot) -> None:
        """Replace the current system snapshot."""
        self._snapshot = snapshot

    @property
    def snapshot(self) -> SystemSnapshot:
        return self._snapshot

    def get_uptime(self) -> float:
        return self._snapshot.uptime

    def get_commands_processed(self) -> int:
        return self._snapshot.commands_processed

    def get_event_queue_depth(self) -> int:
        return self._snapshot.event_queue_depth

    def add_error(self, error: str) -> None:
        """Add an error message to the display."""
        self._snapshot.errors.append(error)
        # Keep last 10 errors
        if len(self._snapshot.errors) > 10:
            self._snapshot.errors = self._snapshot.errors[-10:]

    def clear_errors(self) -> None:
        self._snapshot.errors.clear()

    # ── IPanel interface ───────────────────────────────────────────

    def update(self) -> None:
        """Update uptime from boot time."""
        self._snapshot.uptime = time.time() - self._boot_time

    def paint(self) -> None:
        pass
