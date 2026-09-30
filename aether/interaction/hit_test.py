"""HitTest — maps cursor position to panel under cursor.

Used by InteractionController to determine which panel
the cursor is hovering over, for selection and interaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from aether.ui.panel.panel_info import PanelInfo


@dataclass
class HitResult:
    """Result of a hit test."""

    hit: bool
    panel_id: Optional[str] = None
    panel_info: Optional[PanelInfo] = None
    x: float = 0.0          # Cursor x relative to panel
    y: float = 0.0          # Cursor y relative to panel
    is_resize_handle: bool = False  # True if cursor is on resize handle

    @property
    def panel_type(self) -> Optional[str]:
        return self.panel_info.type if self._panel_info else None


class HitTest:
    """Determine which panel is under the cursor.

    Checks panels in reverse z-order (highest z first).
    Panels that are not visible are skipped.
    """

    def __init__(self, margin: int = 4) -> None:
        self._margin = margin  # Extra hit area around panels

    def test(self, cursor_x: float, cursor_y: float, panels: list[PanelInfo]) -> HitResult:
        """Test cursor position against all panels.

        Args:
            cursor_x: Cursor x in screen coordinates
            cursor_y: Cursor y in screen coordinates
            panels: List of PanelInfo to test against (will be sorted by z-index)

        Returns:
            HitResult with the topmost panel under cursor, or miss.
        """
        # Sort by z-index descending (check topmost first)
        sorted_panels = sorted(panels, key=lambda p: p.z_index, reverse=True)

        for panel in sorted_panels:
            if not panel.visible:
                continue

            result = self._test_single(cursor_x, cursor_y, panel)
            if result.hit:
                return result

        return HitResult(hit=False)

    def _test_single(self, cx: float, cy: float, panel: PanelInfo) -> HitResult:
        """Test cursor against a single panel."""
        m = self._margin
        x, y, w, h = panel.x, panel.y, panel.w, panel.h

        # Check if cursor is within panel bounds (with margin)
        if cx >= (x - m) and cx <= (x + w + m) and cy >= (y - m) and cy <= (y + h + m):
            # Check if on resize handle (bottom-right corner)
            handle_size = 16
            is_handle = (
                cx >= (x + w - handle_size) and
                cy >= (y + h - handle_size) and
                cx <= (x + w + m) and
                cy <= (y + h + m)
            )

            return HitResult(
                hit=True,
                panel_id=panel.id,
                panel_info=panel,
                x=cx - x,
                y=cy - y,
                is_resize_handle=is_handle,
            )

        return HitResult(hit=False)
