"""PerformanceSnapshot — type-safe metrics snapshot for the Dashboard.

Produced by PerformancePlugin and delivered via EventType.SYSTEM_METRICS.
The Dashboard widget is a pure view: it only reads this snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class PerformanceSnapshot:
    """Immutable point-in-time view of runtime health.

    v1 fields:
        cpu_percent / memory_percent — system load
        plugins / panels             — subsystem counts

    v2 fields (readiness):
        camera_ready / vision_ready / memory_ready / ai_ready / voice_ready
        — operational readiness of each subsystem, derived from plugin
          `is_ready()` (real state), never from container registration.

    Future versions extend with scheduler latency, etc.
    """

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    plugins: int = 0
    panels: int = 0
    camera_fps: float = 0.0
    hand_fps: float = 0.0
    camera_ready: bool = False
    vision_ready: bool = False
    memory_ready: bool = False
    ai_ready: bool = False
    voice_ready: bool = False
