"""PerformancePlugin — publishes SYSTEM_METRICS snapshots on the tick loop.

Architecture:
    PerformancePlugin.update(dt)
        → accumulates elapsed time
        → every TICK_INTERVAL collects a PerformanceSnapshot
        → publishes Event(EventType.SYSTEM_METRICS, payload=snapshot)

Consumers:
    DashboardPanelWidget subscribes to SYSTEM_METRICS and renders the snapshot.

Version 1: CPU, memory, plugin count, panel count.
Future versions: camera FPS, hand FPS, scheduler/latency metrics.
"""

from __future__ import annotations

import logging
from typing import Optional

from aether.core.event_bus_v2 import Event
from aether.core.event_type import EventType
from aether.core.performance_snapshot import PerformanceSnapshot
from aether.core.plugin import TickablePlugin, PluginMetadata
from aether.core.service_container import ServiceContainer

logger = logging.getLogger("Aether.PerformancePlugin")

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False


class PerformancePlugin(TickablePlugin):
    """Collects runtime metrics and publishes SYSTEM_METRICS snapshots."""

    name = "performance_plugin"

    TICK_INTERVAL = 0.5  # seconds between snapshots

    def __init__(self) -> None:
        self._container: Optional[ServiceContainer] = None
        self._event_bus = None
        self._elapsed = 0.0
        self._last_snapshot: Optional[PerformanceSnapshot] = None

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            label="Performance",
            version="1.0",
            category="system",
            description="Publishes live runtime metrics for the Dashboard",
        )

    def initialize(self, container: ServiceContainer) -> None:
        self._container = container
        self._event_bus = container.resolve("event_bus")
        logger.info("PerformancePlugin initialized (interval=%.1fs)", self.TICK_INTERVAL)

    def update(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed >= self.TICK_INTERVAL:
            self._elapsed = 0.0
            self._publish_snapshot()

    # ── Snapshot collection ───────────────────────────────────────

    def _collect(self) -> PerformanceSnapshot:
        cpu = 0.0
        mem = 0.0
        if _PSUTIL_AVAILABLE:
            try:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory().percent
            except Exception as e:
                logger.debug("psutil metrics failed: %s", e)

        plugins = 0
        panels = 0
        ready: dict[str, bool] = {}
        if self._container:
            if self._container.has("plugin_loader"):
                loaded = self._container.resolve("plugin_loader").loaded_plugins
                plugins = len(loaded)
                for plugin in loaded:
                    checker = getattr(plugin, "is_ready", None)
                    if callable(checker):
                        try:
                            ready[plugin.name] = bool(checker())
                        except Exception:
                            ready[plugin.name] = False
            if self._container.has("panel_registry"):
                panels = self._container.resolve("panel_registry").panel_count()

        return PerformanceSnapshot(
            cpu_percent=cpu,
            memory_percent=mem,
            plugins=plugins,
            panels=panels,
            camera_ready=ready.get("camera", False),
            vision_ready=ready.get("vision_adapter", False) or ready.get("vision", False),
            memory_ready=ready.get("memory_plugin", False),
            ai_ready=ready.get("ai", False),
            voice_ready=ready.get("voice", False),
        )

    def _publish_snapshot(self) -> None:
        if not self._event_bus:
            return
        self._last_snapshot = self._collect()
        self._event_bus.publish(Event(
            type=EventType.SYSTEM_METRICS,
            payload=self._last_snapshot,
            source=self.name,
        ))

    @property
    def last_snapshot(self) -> Optional[PerformanceSnapshot]:
        return self._last_snapshot

    def shutdown(self) -> None:
        logger.info("PerformancePlugin shutdown")
