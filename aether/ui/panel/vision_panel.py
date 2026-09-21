"""VisionPanel — displays live vision feed status and detected objects.

Stateless renderer — reads from OverlayModel.
Shows: detected objects, hands, camera status, FPS.

Panel type: 'vision'
Z-index: 10
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from aether.ui.panel.abstract_panel import AbstractPanel


@dataclass
class VisionSnapshot:
    """Current vision state for display."""

    fps: float = 0.0
    camera_active: bool = False
    object_count: int = 0
    hand_count: int = 0
    tracking: bool = True
    objects: List[Dict[str, Any]] = field(default_factory=list)
    hands: List[Dict[str, Any]] = field(default_factory=list)


class VisionPanel(AbstractPanel):
    """Displays live vision feed status.

    Stateless renderer — reads from VisionSnapshot.
    Updated by OverlayController or VisionEventAdapter.
    """

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 400,
        height: int = 300,
    ) -> None:
        super().__init__(
            panel_id="vision",
            x=x,
            y=y,
            width=width,
            height=height,
            z_index=10,
        )
        self._snapshot = VisionSnapshot()

    # ── Data model ─────────────────────────────────────────────────

    def update_snapshot(self, snapshot: VisionSnapshot) -> None:
        """Replace the current vision snapshot."""
        self._snapshot = snapshot

    @property
    def snapshot(self) -> VisionSnapshot:
        return self._snapshot

    def get_fps(self) -> float:
        return self._snapshot.fps

    def get_object_count(self) -> int:
        return self._snapshot.object_count

    def get_hand_count(self) -> int:
        return self._snapshot.hand_count

    def is_camera_active(self) -> bool:
        return self._snapshot.camera_active

    def is_tracking(self) -> bool:
        return self._snapshot.tracking

    # ── IPanel interface ───────────────────────────────────────────

    def update(self) -> None:
        pass

    def paint(self) -> None:
        pass
