"""BootProfiler — measures boot time for each stage.

Usage:
    profiler = BootProfiler()
    profiler.mark("config_load")
    # ... do work ...
    profiler.mark("plugins_loaded")
    profiler.log_summary()

Also supports --profile-boot flag for runtime profiling.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("Aether.BootProfiler")


@dataclass
class BootMark:
    """Single timing mark."""
    name: str
    timestamp: float
    elapsed_ms: float = 0.0


@dataclass
class BootProfiler:
    """Measures boot time for each stage.

    Usage:
        profiler = BootProfiler()
        profiler.mark("config_load")
        # ... do work ...
        profiler.mark("plugins_loaded")
        profiler.log_summary()
    """

    _marks: List[BootMark] = field(default_factory=list)
    _start_time: float = 0.0
    _enabled: bool = True

    def __post_init__(self) -> None:
        self._start_time = time.perf_counter()

    def mark(self, name: str) -> None:
        """Record a timing mark."""
        if not self._enabled:
            return

        now = time.perf_counter()
        elapsed_ms = (now - self._start_time) * 1000.0

        # Calculate delta from last mark
        delta_ms = 0.0
        if self._marks:
            delta_ms = elapsed_ms - self._marks[-1].elapsed_ms

        self._marks.append(BootMark(
            name=name,
            timestamp=now,
            elapsed_ms=elapsed_ms,
        ))

        logger.debug("BootProfiler: %s at %.1fms (delta: %.1fms)", name, elapsed_ms, delta_ms)

    def log_summary(self) -> None:
        """Log a summary of all boot stages."""
        if not self._marks:
            return

        total_ms = self._marks[-1].elapsed_ms
        lines = ["Boot time profile:"]
        lines.append(f"  {'Stage':<30} {'Total':>10} {'Delta':>10}")
        lines.append(f"  {'-'*30} {'-'*10} {'-'*10}")

        prev_ms = 0.0
        for mark in self._marks:
            delta = mark.elapsed_ms - prev_ms
            lines.append(f"  {mark.name:<30} {mark.elapsed_ms:>9.1f}ms {delta:>9.1f}ms")
            prev_ms = mark.elapsed_ms

        lines.append(f"  {'-'*30} {'-'*10} {'-'*10}")
        lines.append(f"  {'TOTAL':<30} {total_ms:>9.1f}ms")

        summary = "\n".join(lines)
        logger.info("\n%s", summary)

        # Also print to console for visibility
        print(f"\n{'='*60}")
        print(summary)
        print(f"{'='*60}\n")

    def get_total_ms(self) -> float:
        """Get total boot time in milliseconds."""
        if not self._marks:
            return 0.0
        return self._marks[-1].elapsed_ms

    def get_stage_ms(self, name: str) -> Optional[float]:
        """Get elapsed time for a specific stage."""
        for mark in self._marks:
            if mark.name == name:
                return mark.elapsed_ms
        return None

    def get_delta_ms(self, name: str) -> float:
        """Get time delta from previous mark to this mark."""
        for i, mark in enumerate(self._marks):
            if mark.name == name:
                if i == 0:
                    return mark.elapsed_ms
                return mark.elapsed_ms - self._marks[i - 1].elapsed_ms
        return 0.0

    def disable(self) -> None:
        """Disable profiling (no-ops mark calls)."""
        self._enabled = False

    def enable(self) -> None:
        """Enable profiling."""
        self._enabled = True


# Global instance for convenience
boot_profiler = BootProfiler()
