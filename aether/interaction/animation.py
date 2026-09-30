"""PanelAnimation — smooth lerp transitions for panel geometry.

Computes interpolated positions/sizes each frame.
OverlayWidget reads from OverlayModel.animation_state to render smooth motion.

Architecture:
    InteractionBridge → OverlayModel.animation_state → OverlayWidget
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


LERP_SPEED = 8.0  # units/second — higher = faster snap


@dataclass
class AnimatedPanel:
    """Smoothly animated panel geometry."""
    panel_id: str = ""
    current_x: float = 0.0
    current_y: float = 0.0
    current_w: float = 0.0
    current_h: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    target_w: float = 0.0
    target_h: float = 0.0
    opacity: float = 1.0
    target_opacity: float = 1.0
    visible: bool = True


class AnimationManager:
    """Drives smooth panel transitions via lerp.

    Each frame, call update(dt) to interpolate all animated panels
    toward their targets. Widget reads from overlay_model for rendering.
    """

    def __init__(self) -> None:
        self._panels: dict[str, AnimatedPanel] = {}

    @property
    def panels(self) -> dict[str, AnimatedPanel]:
        return dict(self._panels)

    def get(self, panel_id: str) -> Optional[AnimatedPanel]:
        return self._panels.get(panel_id)

    def has(self, panel_id: str) -> bool:
        return panel_id in self._panels

    def ensure(self, panel_id: str) -> AnimatedPanel:
        if panel_id not in self._panels:
            self._panels[panel_id] = AnimatedPanel(panel_id=panel_id)
        return self._panels[panel_id]

    def move_to(self, panel_id: str, x: int, y: int) -> None:
        anim = self.ensure(panel_id)
        anim.target_x = float(x)
        anim.target_y = float(y)

    def resize_to(self, panel_id: str, w: int, h: int) -> None:
        anim = self.ensure(panel_id)
        anim.target_w = float(w)
        anim.target_h = float(h)

    def set_geometry(self, panel_id: str, x: int, y: int, w: int, h: int) -> None:
        anim = self.ensure(panel_id)
        anim.current_x = float(x)
        anim.current_y = float(y)
        anim.current_w = float(w)
        anim.current_h = float(h)
        anim.target_x = float(x)
        anim.target_y = float(y)
        anim.target_w = float(w)
        anim.target_h = float(h)

    def show(self, panel_id: str, instant: bool = False) -> None:
        anim = self.ensure(panel_id)
        if instant:
            anim.opacity = 1.0
        anim.target_opacity = 1.0

    def hide(self, panel_id: str, instant: bool = False) -> None:
        anim = self.ensure(panel_id)
        if instant:
            anim.opacity = 0.0
        anim.target_opacity = 0.0

    def remove(self, panel_id: str) -> None:
        self._panels.pop(panel_id, None)

    def update(self, dt: float) -> set[str]:
        """Lerp all panels toward targets. Returns set of dirty panel_ids."""
        dirty: set[str] = set()
        for pid, anim in self._panels.items():
            changed = False
            anim.current_x = _lerp(anim.current_x, anim.target_x, dt)
            anim.current_y = _lerp(anim.current_y, anim.target_y, dt)
            anim.current_w = _lerp(anim.current_w, anim.target_w, dt)
            anim.current_h = _lerp(anim.current_h, anim.target_h, dt)
            anim.opacity = _lerp(anim.opacity, anim.target_opacity, dt)

            if anim.opacity < 0.01 and anim.target_opacity < 0.01:
                anim.visible = False
            else:
                anim.visible = True

            if abs(anim.current_x - anim.target_x) > 0.5:
                changed = True
            if abs(anim.current_y - anim.target_y) > 0.5:
                changed = True
            if abs(anim.current_w - anim.target_w) > 0.5:
                changed = True
            if abs(anim.current_h - anim.target_h) > 0.5:
                changed = True
            if abs(anim.opacity - anim.target_opacity) > 0.01:
                changed = True

            if changed:
                dirty.add(pid)

        return dirty

    def clear(self) -> None:
        self._panels.clear()


def _lerp(current: float, target: float, dt: float, speed: float = LERP_SPEED) -> float:
    """Exponential ease-out lerp."""
    if abs(current - target) < 0.1:
        return target
    diff = target - current
    step = diff * (1.0 - pow(2.0, -speed * dt))
    return current + step
