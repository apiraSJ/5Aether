"""SnapZoneManager — edge/center/panel snap for drag operations.

Architecture:
    InteractionController → SnapZoneManager (during drag)

Snap types:
    EDGE_TOP / EDGE_BOTTOM / EDGE_LEFT / EDGE_RIGHT
    CENTER
    DOCK_LEFT / DOCK_RIGHT / DOCK_TOP / DOCK_BOTTOM / DOCK_FULL
    PANEL_ALIGN_LEFT / PANEL_ALIGN_RIGHT / PANEL_ALIGN_TOP / PANEL_ALIGN_BOTTOM

Flow:
    on_cursor_move → DragController.update → SnapZoneManager.find_snap
    → snap to nearest zone if within threshold → apply snapped position
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from aether.ui.panel.panel_registry import PanelRegistry

logger = logging.getLogger("Aether.SnapZoneManager")


class SnapType(Enum):
    NONE = "none"
    EDGE_LEFT = "edge_left"
    EDGE_RIGHT = "edge_right"
    EDGE_TOP = "edge_top"
    EDGE_BOTTOM = "edge_bottom"
    CENTER = "center"
    DOCK_LEFT = "dock_left"
    DOCK_RIGHT = "dock_right"
    DOCK_TOP = "dock_top"
    DOCK_BOTTOM = "dock_bottom"
    DOCK_FULL = "dock_full"
    PANEL_ALIGN_LEFT = "panel_align_left"
    PANEL_ALIGN_RIGHT = "panel_align_right"
    PANEL_ALIGN_TOP = "panel_align_top"
    PANEL_ALIGN_BOTTOM = "panel_align_bottom"


@dataclass
class SnapResult:
    """Result from a snap query."""

    active: bool = False
    snap_type: SnapType = SnapType.NONE
    target_x: int = 0
    target_y: int = 0
    target_w: Optional[int] = None
    target_h: Optional[int] = None
    indicator_x: int = 0
    indicator_y: int = 0
    indicator_w: int = 0
    indicator_h: int = 0


@dataclass
class SnapZone:
    """A snap zone with position and type."""
    snap_type: SnapType
    x: int
    y: int
    w: int
    h: int


class SnapZoneManager:
    """Computes snap positions during drag operations.

    Threshold configurable. Call find_snap each frame during drag.
    Only snaps when panel center/edge is within threshold of a zone.
    """

    def __init__(
        self,
        registry: PanelRegistry,
        screen_width: int = 1920,
        screen_height: int = 1080,
        snap_threshold: int = 30,
        dock_ratio: float = 0.5,
    ) -> None:
        self._registry = registry
        self._screen_w = screen_width
        self._screen_h = screen_height
        self._threshold = snap_threshold
        self._dock_ratio = dock_ratio
        self._active_zones: list[SnapZone] = []

    @property
    def threshold(self) -> int:
        return self._threshold

    @threshold.setter
    def threshold(self, value: int) -> None:
        self._threshold = max(10, min(100, value))

    @property
    def active_zones(self) -> list[SnapZone]:
        return list(self._active_zones)

    def set_screen_size(self, width: int, height: int) -> None:
        self._screen_w = width
        self._screen_h = height

    def find_snap(
        self,
        panel_x: int,
        panel_y: int,
        panel_w: int,
        panel_h: int,
        exclude_id: Optional[str] = None,
    ) -> SnapResult:
        """Check if the panel should snap to any zone.

        Returns SnapResult with snap details.
        Only one snap type is returned (closest match wins).
        Priority: edge > dock > center > panel align.
        """
        zones = self._build_zones(exclude_id)
        self._active_zones = zones

        cx = panel_x + panel_w // 2
        cy = panel_y + panel_h // 2
        panel_right = panel_x + panel_w
        panel_bottom = panel_y + panel_h

        best: Optional[SnapResult] = None
        best_dist = float("inf")

        for zone in zones:
            dist = self._distance_to_zone(panel_x, panel_y, panel_w, panel_h, zone)
            if dist is None or dist > self._threshold:
                continue

            is_vertical = zone.snap_type in (SnapType.EDGE_LEFT, SnapType.EDGE_RIGHT,
                                              SnapType.DOCK_LEFT, SnapType.DOCK_RIGHT)
            is_horizontal = zone.snap_type in (SnapType.EDGE_TOP, SnapType.EDGE_BOTTOM,
                                               SnapType.DOCK_TOP, SnapType.DOCK_BOTTOM)

            tx, ty = panel_x, panel_y
            tw, th = panel_w, panel_h

            if zone.snap_type == SnapType.EDGE_LEFT:
                tx = zone.x
            elif zone.snap_type == SnapType.EDGE_RIGHT:
                tx = zone.x - panel_w
            elif zone.snap_type == SnapType.EDGE_TOP:
                ty = zone.y
            elif zone.snap_type == SnapType.EDGE_BOTTOM:
                ty = zone.y - panel_h
            elif zone.snap_type == SnapType.CENTER:
                tx = zone.x
                ty = zone.y
            elif zone.snap_type == SnapType.DOCK_FULL:
                tx, ty = zone.x, zone.y
                tw, th = zone.w, zone.h
            elif zone.snap_type in (SnapType.DOCK_LEFT, SnapType.DOCK_RIGHT,
                                     SnapType.DOCK_TOP, SnapType.DOCK_BOTTOM):
                tx, ty = zone.x, zone.y
                tw, th = zone.w, zone.h
            elif zone.snap_type in (SnapType.PANEL_ALIGN_LEFT, SnapType.PANEL_ALIGN_RIGHT,
                                     SnapType.PANEL_ALIGN_TOP, SnapType.PANEL_ALIGN_BOTTOM):
                tx, ty = zone.x, zone.y

            result = SnapResult(
                active=True,
                snap_type=zone.snap_type,
                target_x=tx,
                target_y=ty,
                target_w=tw if tw != panel_w else None,
                target_h=th if th != panel_h else None,
                indicator_x=zone.x,
                indicator_y=zone.y,
                indicator_w=zone.w,
                indicator_h=zone.h,
            )

            if dist < best_dist:
                best_dist = dist
                best = result

        if best is not None:
            logger.debug("Snap: %s → (%d, %d) [dist=%d]",
                          best.snap_type.value, best.target_x, best.target_y, best_dist)

        return best or SnapResult()

    def is_snapped(self, panel_x: int, panel_y: int, panel_w: int, panel_h: int) -> bool:
        """Check if panel is at a snap position."""
        return self.find_snap(panel_x, panel_y, panel_w, panel_h).active

    def clear_active_zones(self) -> None:
        self._active_zones.clear()

    def _build_zones(self, exclude_id: Optional[str] = None) -> list[SnapZone]:
        """Build all snap zones based on screen edges and panels."""
        zones: list[SnapZone] = []

        # Edge zones (point-snaps: snap panel edge to screen edge)
        zones.append(SnapZone(SnapType.EDGE_LEFT, 0, 0, 1, self._screen_h))
        zones.append(SnapZone(SnapType.EDGE_RIGHT, self._screen_w, 0, 1, self._screen_h))
        zones.append(SnapZone(SnapType.EDGE_TOP, 0, 0, self._screen_w, 1))
        zones.append(SnapZone(SnapType.EDGE_BOTTOM, 0, self._screen_h, self._screen_w, 1))

        # Dock zones (resize panel to region)
        dw = int(self._screen_w * self._dock_ratio)
        dh = int(self._screen_h * self._dock_ratio)
        zones.append(SnapZone(SnapType.DOCK_LEFT, 0, 0, dw, self._screen_h))
        zones.append(SnapZone(SnapType.DOCK_RIGHT, self._screen_w - dw, 0, dw, self._screen_h))
        zones.append(SnapZone(SnapType.DOCK_TOP, 0, 0, self._screen_w, dh))
        zones.append(SnapZone(SnapType.DOCK_BOTTOM, 0, self._screen_h - dh, self._screen_w, dh))
        zones.append(SnapZone(SnapType.DOCK_FULL, 0, 0, self._screen_w, self._screen_h))

        # Center zone
        cx = (self._screen_w - 600) // 2
        cy = (self._screen_h - 400) // 2
        zones.append(SnapZone(SnapType.CENTER, cx, cy, 1, 1))

        return zones

    def _distance_to_zone(
        self, px: int, py: int, pw: int, ph: int, zone: SnapZone
    ) -> Optional[float]:
        """Compute distance from panel to snap zone.

        Returns None if zone type doesn't apply (panel align needs other panels).
        Returns Manhattan distance for edge/center, box overlap distance for docks.
        """
        pr = px + pw
        pb = py + ph

        if zone.snap_type == SnapType.EDGE_LEFT:
            return abs(float(px))
        elif zone.snap_type == SnapType.EDGE_RIGHT:
            return abs(float(pr - self._screen_w))
        elif zone.snap_type == SnapType.EDGE_TOP:
            return abs(float(py))
        elif zone.snap_type == SnapType.EDGE_BOTTOM:
            return abs(float(pb - self._screen_h))
        elif zone.snap_type == SnapType.CENTER:
            zone_cx = zone.x + 300
            zone_cy = zone.y + 200
            pcx = px + pw // 2
            pcy = py + ph // 2
            return abs(pcx - zone_cx) + abs(pcy - zone_cy)
        elif zone.snap_type in (SnapType.DOCK_LEFT, SnapType.DOCK_RIGHT,
                                 SnapType.DOCK_TOP, SnapType.DOCK_BOTTOM,
                                 SnapType.DOCK_FULL):
            return self._box_distance(px, py, pw, ph, zone.x, zone.y, zone.w, zone.h)
        elif zone.snap_type in (SnapType.PANEL_ALIGN_LEFT, SnapType.PANEL_ALIGN_RIGHT,
                                 SnapType.PANEL_ALIGN_TOP, SnapType.PANEL_ALIGN_BOTTOM):
            return None  # Not yet implemented for panel-to-panel align
        return None

    @staticmethod
    def _box_distance(
        x1: int, y1: int, w1: int, h1: int,
        x2: int, y2: int, w2: int, h2: int,
    ) -> float:
        """Minimum distance between two rectangles (Manhattan center)."""
        c1x = x1 + w1 // 2
        c1y = y1 + h1 // 2
        c2x = x2 + w2 // 2
        c2y = y2 + h2 // 2
        return abs(c1x - c2x) + abs(c1y - c2y)
