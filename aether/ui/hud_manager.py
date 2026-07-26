"""HUDManager — manages widget layers, z-order, animation, and rendering.

Widgets are stateless renderers that read from OverlayModel.
HUDManager handles the visual composition:
  - Layer ordering (background → overlay → status → foreground)
  - Z-order within layers
  - Throttling: expensive layers update less frequently (adaptive)
  - Visibility scheduling: hidden/inactive widgets sleep
  - Dirty region tracking for partial repaint
  - Render pipeline (update → paint)

Data flow:
    OverlayModel → Widgets → HUDManager → Screen

HUDManager never modifies data. It only orchestrates rendering.
"""

from __future__ import annotations

import logging
import time
from typing import Protocol

from aether.core.profiler import profiler
from aether.core.adaptive_scheduler import adaptive_scheduler, SchedulerState

logger = logging.getLogger("Aether.HUDManager")


class Widget(Protocol):
    """Protocol for widgets managed by HUDManager."""

    def update(self) -> None:
        """Update widget state from OverlayModel."""
        ...

    def paint(self) -> None:
        """Render widget to screen."""
        ...

    def is_visible(self) -> bool:
        """Check if widget is visible and should be rendered."""
        ...

    def get_dirty_rect(self) -> tuple[float, float, float, float] | None:
        """Get dirty region (x, y, w, h) if widget needs partial repaint.
        Returns None for full repaint."""
        ...


# Default update intervals per layer (seconds)
# Layer 0 (camera): every frame (0 = no throttle)
# Layer 1 (overlay): every frame
# Layer 2 (status/gesture/object list): every 0.1s = 10 Hz
# Layer 3 (timeline/perf_hud): every 0.2s = 5 Hz
DEFAULT_LAYER_INTERVALS = {
    0: 0.0,     # camera — every frame
    1: 0.0,     # overlay — every frame
    2: 0.1,     # status/gesture/objects — 10 Hz
    3: 0.2,     # timeline/perf_hud — 5 Hz
}


class HUDManager:
    """Manages widget layers, z-order, animation, and rendering.

    Optimization: each layer has a minimum update interval.
    Widgets in higher-numbered layers update less frequently.
    Supports adaptive intervals from AdaptiveScheduler.
    Supports widget visibility scheduling (skip hidden/inactive).
    Supports dirty region tracking for partial repaint.
    """

    def __init__(self, layer_intervals: dict[int, float] | None = None) -> None:
        self._layers: dict[int, list[Widget]] = {}
        self._layer_order: list[int] = []
        self._layer_intervals = layer_intervals or DEFAULT_LAYER_INTERVALS.copy()
        self._layer_last_update: dict[int, float] = {}
        self._adaptive_enabled = True
        self._scheduler_state: SchedulerState | None = None
        self._dirty_rects: list[tuple[float, float, float, float]] = []

    def add_widget(self, widget: Widget, layer: int = 0) -> None:
        """Add a widget to a specific layer."""
        if layer not in self._layers:
            self._layers[layer] = []
            self._layer_order.append(layer)
            self._layer_order.sort()
            self._layer_last_update[layer] = 0.0

        self._layers[layer].append(widget)

    def remove_widget(self, widget: Widget) -> None:
        """Remove a widget from all layers."""
        for layer, widgets in self._layers.items():
            if widget in widgets:
                widgets.remove(widget)
                break

    def enable_adaptive(self, enabled: bool = True) -> None:
        """Enable/disable adaptive scheduling from AdaptiveScheduler."""
        self._adaptive_enabled = enabled

    def _get_effective_interval(self, layer: int) -> float:
        """Get effective interval for layer, considering adaptive scheduler."""
        if not self._adaptive_enabled:
            return self._layer_intervals.get(layer, 0.0)

        # Update scheduler state if needed
        if self._scheduler_state is None:
            self._scheduler_state = adaptive_scheduler.get_state()

        adaptive_intervals = self._scheduler_state.layer_intervals
        return adaptive_intervals.get(layer, self._layer_intervals.get(layer, 0.0))

    def update(self) -> None:
        """Update all visible widgets, respecting per-layer throttling.

        - Skips invisible widgets (sleep mode)
        - Respects adaptive layer intervals
        - Collects dirty rects for partial repaint
        """
        now = time.perf_counter()

        # Refresh adaptive intervals periodically
        if self._adaptive_enabled:
            self._scheduler_state = adaptive_scheduler.get_state()

        self._dirty_rects.clear()

        for layer in self._layer_order:
            interval = self._get_effective_interval(layer)
            last = self._layer_last_update.get(layer, 0.0)
            if interval > 0 and (now - last) < interval:
                continue  # Skip — not time yet for this layer

            self._layer_last_update[layer] = now

            for widget in self._layers.get(layer, []):
                # Skip invisible widgets entirely (no update, no paint)
                if hasattr(widget, 'is_visible') and not widget.is_visible():
                    continue

                try:
                    widget.update()
                except Exception:
                    logger.exception("Widget update failed in layer %d", layer)

                # Collect dirty rect for partial repaint
                if hasattr(widget, 'get_dirty_rect'):
                    rect = widget.get_dirty_rect()
                    if rect is not None:
                        self._dirty_rects.append(rect)

    def paint(self, widget: 'Widget' | None = None) -> None:
        """Paint widgets.

        If widget is specified, paint only that widget (for dirty region).
        Otherwise paint all visible widgets across all layers.
        """
        t0 = time.perf_counter()

        if widget is not None:
            # Single widget paint (for dirty region)
            if widget.is_visible():
                try:
                    widget.paint()
                except Exception:
                    logger.exception("Widget paint failed")
        else:
            # Full paint - all visible widgets
            for layer in self._layer_order:
                for widget in self._layers.get(layer, []):
                    if hasattr(widget, 'is_visible') and not widget.is_visible():
                        continue
                    try:
                        widget.paint()
                    except Exception:
                        logger.exception("Widget paint failed in layer %d", layer)

        ms = (time.perf_counter() - t0) * 1000.0
        profiler._record_stage("render", ms)

    def get_dirty_rects(self) -> list[tuple[float, float, float, float]]:
        """Get accumulated dirty rects for partial repaint."""
        return self._dirty_rects.copy()

    def clear(self) -> None:
        """Remove all widgets."""
        self._layers.clear()
        self._layer_order.clear()
        self._layer_last_update.clear()

    @property
    def widget_count(self) -> int:
        return sum(len(widgets) for widgets in self._layers.values())

    @property
    def layers(self) -> list[int]:
        return list(self._layer_order)

    @property
    def visible_widget_count(self) -> int:
        """Count of currently visible widgets."""
        count = 0
        for layer in self._layer_order:
            for widget in self._layers.get(layer, []):
                if hasattr(widget, 'is_visible') and widget.is_visible():
                    count += 1
        return count