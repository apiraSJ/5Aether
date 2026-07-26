"""Profiler — central performance metrics collector for Aether vision pipeline.

Measures:
  - Per-stage timing (Camera, YOLO, MediaPipe, VisionAdapter, EventBus flush, Render)
  - End-to-End Latency (camera capture → screen render)
  - Frame Age (age of frame being processed)
  - Tick Overrun (budget vs actual tick time)
  - Queue depths (FrameBroker, EventBus)

Supports two modes:
  1. Live HUD mode — 1-second window aggregation (low overhead)
  2. Recording mode — full history for percentile reports (--profile)

Usage:
    from aether.core.profiler import profiler

    # Live HUD (always on)
    snapshot = profiler.snapshot()

    # Recording for report
    profiler.start_recording()
    ...run for N seconds...
    report = profiler.report()
    profiler.stop_recording()

    # Auto-save report to file
    profiler.start_recording()
    ...run...
    profiler.stop_recording(save_to="profile_results.txt")  # saves report + auto-saves
"""

from __future__ import annotations

import logging
import statistics
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger("Aether.Profiler")


@dataclass
class StageMetrics:
    """Accumulated metrics for a single pipeline stage."""
    total_ms: float = 0.0
    count: int = 0
    min_ms: float = 999999.0
    max_ms: float = 0.0
    last_ms: float = 0.0
    _window_ms: float = 0.0
    _window_count: int = 0
    _history: list[float] = field(default_factory=list)

    def record(self, ms: float) -> None:
        self.total_ms += ms
        self.count += 1
        self.last_ms = ms
        if ms < self.min_ms:
            self.min_ms = ms
        if ms > self.max_ms:
            self.max_ms = ms
        self._window_ms += ms
        self._window_count += 1

    def window_avg(self) -> float:
        if self._window_count == 0:
            return 0.0
        return self._window_ms / self._window_count

    def window_count(self) -> int:
        return self._window_count

    def reset_window(self) -> tuple[float, int]:
        avg = self.window_avg()
        cnt = self._window_count
        self._window_ms = 0.0
        self._window_count = 0
        return avg, cnt

    def percentile(self, p: float) -> float:
        """Compute percentile from history."""
        if not self._history:
            return 0.0
        sorted_h = sorted(self._history)
        idx = int(len(sorted_h) * p / 100.0)
        idx = min(idx, len(sorted_h) - 1)
        return sorted_h[idx]


@dataclass
class QueueMetrics:
    """Queue depth / throughput metrics."""
    depth: int = 0
    flush_ms: float = 0.0
    events_per_sec: float = 0.0
    dropped: int = 0
    overwritten: int = 0
    oldest_ms: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass
class ProfilerSnapshot:
    """Point-in-time snapshot of all metrics."""
    timestamp: float
    stages: dict[str, dict]
    queues: dict[str, dict]
    e2e_latency_ms: float
    frame_age_ms: float
    tick_budget_ms: float
    tick_used_ms: float
    tick_overrun_ms: float
    tick_fps: float
    render_ms: float


@dataclass
class PerfReport:
    """Full-session performance report with percentiles."""
    duration_s: float
    stages: dict[str, dict]  # name -> {avg, p50, p95, max, count}
    e2e: dict  # {avg, p50, p95, max}
    frame_age: dict  # {avg, p50, p95, max}
    tick: dict  # {avg, budget, overruns, overrun_pct}
    queues: dict[str, dict]
    verdicts: list[str]  # Performance budget violations


class Profiler:
    """Thread-safe central profiler. Collects timing and queue metrics."""

    def __init__(self, log_interval: float = 1.0) -> None:
        self._log_interval = log_interval
        self._stages: dict[str, StageMetrics] = {}
        self._queues: dict[str, QueueMetrics] = {}
        self._lock = threading.Lock()
        self._last_log_time = time.perf_counter()
        self._enabled = True

        # Live metrics
        self._e2e_latency_ms: float = 0.0
        self._frame_age_ms: float = 0.0
        self._tick_budget_ms: float = 33.3
        self._tick_used_ms: float = 0.0
        self._tick_overrun_ms: float = 0.0
        self._tick_count: int = 0
        self._tick_window_start: float = time.perf_counter()
        self._tick_fps: float = 0.0

        # Recording mode
        self._recording: bool = False
        self._record_start: float = 0.0
        self._e2e_history: list[float] = []
        self._frame_age_history: list[float] = []
        self._tick_used_history: list[float] = []
        self._tick_overrun_count: int = 0
        self._tick_total_count: int = 0

    def now(self) -> float:
        return time.perf_counter()

    # ── Recording ───────────────────────────────────────────────────

    def start_recording(self) -> None:
        """Start full-session recording for report generation."""
        with self._lock:
            self._recording = True
            self._record_start = time.perf_counter()
            self._e2e_history.clear()
            self._frame_age_history.clear()
            self._tick_used_history.clear()
            self._tick_overrun_count = 0
            self._tick_total_count = 0
            for stage in self._stages.values():
                stage._history.clear()
        logger.info("Profiler recording started")

    def stop_recording(self, save_to: str | None = None) -> PerfReport | None:
        """Stop recording. Optionally save report to file.

        Args:
            save_to: If set, saves formatted report to this path.
                     Returns the report.

        Returns:
            PerfReport if recording was active, None otherwise.
        """
        was_recording = False
        with self._lock:
            was_recording = self._recording
            self._recording = False
        if not was_recording:
            return None
        report = self.report()
        if report and save_to:
            try:
                from pathlib import Path
                path = Path(save_to)
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.format_report(report))
                    f.write("\n\n--- Raw Data ---\n")
                    import json
                    f.write(json.dumps({
                        "duration_s": report.duration_s,
                        "stages": report.stages,
                        "e2e": report.e2e,
                        "frame_age": report.frame_age,
                        "tick": report.tick,
                        "queues": report.queues,
                        "verdicts": report.verdicts,
                    }, indent=2))
                logger.info("Profile report saved to %s", path.resolve())
            except Exception as exc:
                logger.error("Failed to save profile report: %s", exc)
        logger.info("Profiler recording stopped")
        return report

    @property
    def is_recording(self) -> bool:
        return self._recording

    # ── Stage timing ────────────────────────────────────────────────

    @contextmanager
    def measure(self, name: str):
        if not self._enabled:
            yield
            return
        t0 = time.perf_counter()
        try:
            yield
        finally:
            ms = (time.perf_counter() - t0) * 1000.0
            self._record_stage(name, ms)

    def begin(self, name: str) -> float:
        return time.perf_counter()

    def end(self, name: str, t0: float) -> float:
        ms = (time.perf_counter() - t0) * 1000.0
        self._record_stage(name, ms)
        return ms

    def _record_stage(self, name: str, ms: float) -> None:
        with self._lock:
            if name not in self._stages:
                self._stages[name] = StageMetrics()
            stage = self._stages[name]
            stage.record(ms)
            if self._recording:
                stage._history.append(ms)

    # ── End-to-End Latency ─────────────────────────────────────────

    def record_render(self, capture_ts: float) -> None:
        latency_ms = (time.perf_counter() - capture_ts) * 1000.0
        with self._lock:
            self._e2e_latency_ms = latency_ms
            if self._recording:
                self._e2e_history.append(latency_ms)

    # ── Frame Age ──────────────────────────────────────────────────

    def set_frame_age(self, age_ms: float) -> None:
        with self._lock:
            self._frame_age_ms = age_ms
            if self._recording:
                self._frame_age_history.append(age_ms)

    # ── Tick Budget ────────────────────────────────────────────────

    def tick_begin(self, budget_ms: float = 33.3) -> None:
        self._tick_budget_ms = budget_ms
        self._tick_start = time.perf_counter()

    def tick_end(self) -> None:
        if not hasattr(self, "_tick_start"):
            return
        used_ms = (time.perf_counter() - self._tick_start) * 1000.0
        overrun = max(0.0, used_ms - self._tick_budget_ms)

        with self._lock:
            self._tick_used_ms = used_ms
            self._tick_overrun_ms = overrun
            self._tick_total_count += 1
            if overrun > 0:
                self._tick_overrun_count += 1
            if self._recording:
                self._tick_used_history.append(used_ms)

            now = time.perf_counter()
            elapsed = now - self._tick_window_start
            if elapsed >= 1.0:
                self._tick_fps = self._tick_count / elapsed
                self._tick_count = 0
                self._tick_window_start = now
            self._tick_count += 1

    # ── Plugin timing ──────────────────────────────────────────────

    def record_plugin_time(self, name: str, ms: float) -> None:
        """Record time spent in a plugin's update() call."""
        self._record_stage(f"plugin.{name}", ms)

    # ── Queue metrics ──────────────────────────────────────────────

    def set_queue(self, name: str, **kwargs) -> None:
        with self._lock:
            if name not in self._queues:
                self._queues[name] = QueueMetrics()
            q = self._queues[name]
            for k, v in kwargs.items():
                if hasattr(q, k):
                    setattr(q, k, v)
                else:
                    q.extra[k] = v

    # ── Snapshot (live HUD) ────────────────────────────────────────

    def snapshot(self) -> ProfilerSnapshot:
        now = time.perf_counter()
        stages = {}
        queues = {}

        with self._lock:
            for name, stage in self._stages.items():
                avg, cnt = stage.reset_window()
                stages[name] = {
                    "avg_ms": round(avg, 1),
                    "last_ms": round(stage.last_ms, 1),
                    "min_ms": round(stage.min_ms, 1),
                    "max_ms": round(stage.max_ms, 1),
                    "fps": round(cnt, 1),
                }
            for name, q in self._queues.items():
                queues[name] = {
                    "depth": q.depth,
                    "flush_ms": round(q.flush_ms, 2),
                    "events_per_sec": round(q.events_per_sec, 1),
                    "dropped": q.dropped,
                    "overwritten": q.overwritten,
                    "oldest_ms": round(q.oldest_ms, 1),
                    **{k: v for k, v in q.extra.items()},
                }

            e2e = self._e2e_latency_ms
            frame_age = self._frame_age_ms
            tick_budget = self._tick_budget_ms
            tick_used = self._tick_used_ms
            tick_overrun = self._tick_overrun_ms
            tick_fps = self._tick_fps
            render_ms = stages.get("render", {}).get("avg_ms", 0.0)

        return ProfilerSnapshot(
            timestamp=now, stages=stages, queues=queues,
            e2e_latency_ms=round(e2e, 1), frame_age_ms=round(frame_age, 1),
            tick_budget_ms=round(tick_budget, 1), tick_used_ms=round(tick_used, 1),
            tick_overrun_ms=round(tick_overrun, 1), tick_fps=round(tick_fps, 1),
            render_ms=round(render_ms, 1),
        )

    # ── Report (full session) ──────────────────────────────────────

    def report(self) -> PerfReport:
        """Generate a full-session performance report from recorded history."""
        duration = time.perf_counter() - self._record_start

        def _stats(values: list[float]) -> dict:
            if not values:
                return {"avg": 0, "p50": 0, "p95": 0, "max": 0, "count": 0}
            s = sorted(values)
            n = len(s)
            return {
                "avg": round(statistics.mean(s), 1),
                "p50": round(s[n // 2], 1),
                "p95": round(s[int(n * 0.95)] if n > 1 else s[0], 1),
                "max": round(s[-1], 1),
                "count": n,
            }

        # Stage stats
        stages = {}
        with self._lock:
            for name, stage in self._stages.items():
                if stage._history:
                    stages[name] = _stats(stage._history)

        # Tick stats
        tick_overrun_pct = 0.0
        if self._tick_total_count > 0:
            tick_overrun_pct = round(self._tick_overrun_count / self._tick_total_count * 100, 1)
        tick = {
            **_stats(self._tick_used_history),
            "budget": round(self._tick_budget_ms, 1),
            "overruns": self._tick_overrun_count,
            "overrun_pct": tick_overrun_pct,
        }

        # Queue stats
        queues = {}
        with self._lock:
            for name, q in self._queues.items():
                queues[name] = {
                    "depth": q.depth,
                    "overwritten": q.overwritten,
                    "oldest_ms": round(q.oldest_ms, 1),
                }

        # Verdicts
        verdicts = []
        budget = {
            "camera": 40, "yolo": 70, "mediapipe": 50, "vision_adapter": 5,
            "render": 5, "eventbus_flush": 5,
        }
        for name, limit in budget.items():
            if name in stages and stages[name]["p95"] > limit:
                verdicts.append(f"{name.upper()} P95={stages[name]['p95']}ms > {limit}ms budget")

        # Plugin verdicts (main thread budget)
        plugin_budget = 10  # 10ms per plugin update is generous
        for name, s in stages.items():
            if name.startswith("plugin.") and s.get("p95", 0) > plugin_budget:
                label = name.replace("plugin.", "")
                verdicts.append(f"PLUGIN.{label.upper()} P95={s['p95']}ms > {plugin_budget}ms main thread budget")

        if tick.get("overrun_pct", 0) > 1:
            verdicts.append(f"Tick overrun {tick['overrun_pct']}% of frames")

        if self._e2e_history:
            e2e_stats = _stats(self._e2e_history)
            if e2e_stats["p95"] > 120:
                verdicts.append(f"End-to-End P95={e2e_stats['p95']}ms > 120ms budget")
        else:
            e2e_stats = {"avg": 0, "p50": 0, "p95": 0, "max": 0, "count": 0}

        if self._frame_age_history:
            fa_stats = _stats(self._frame_age_history)
            if fa_stats["p95"] > 100:
                verdicts.append(f"Frame Age P95={fa_stats['p95']}ms > 100ms budget")
        else:
            fa_stats = {"avg": 0, "p50": 0, "p95": 0, "max": 0, "count": 0}

        if not verdicts:
            verdicts.append("ALL WITHIN BUDGET")

        return PerfReport(
            duration_s=round(duration, 1),
            stages=stages,
            e2e=e2e_stats,
            frame_age=fa_stats,
            tick=tick,
            queues=queues,
            verdicts=verdicts,
        )

    def format_report(self, report: PerfReport | None = None) -> str:
        """Format a PerfReport as a human-readable string."""
        if report is None:
            report = self.report()

        lines = [
            "",
            "=" * 56,
            "  Aether Performance Report",
            "=" * 56,
            f"  Duration: {report.duration_s:.0f} s",
            "",
        ]

        # Pipeline stages
        lines.append("  Pipeline Timing")
        lines.append("  " + "-" * 52)
        lines.append(f"  {'Stage':<16} {'Avg':>7} {'P50':>7} {'P95':>7} {'Max':>7} {'Count':>7}")
        lines.append("  " + "-" * 52)

        stage_order = ["camera", "yolo", "mediapipe", "vision_adapter", "render", "eventbus_flush"]
        for name in stage_order:
            if name in report.stages:
                s = report.stages[name]
                label = name.upper().replace("_", " ")
                lines.append(
                    f"  {label:<16} {s['avg']:>6.1f}ms {s['p50']:>6.1f}ms "
                    f"{s['p95']:>6.1f}ms {s['max']:>6.1f}ms {s['count']:>6}"
                )

        # Plugin stages (main thread)
        plugin_entries = {k: v for k, v in report.stages.items() if k.startswith("plugin.")}
        if plugin_entries:
            lines.append("")
            lines.append("  Plugins (Main Thread)")
            lines.append("  " + "-" * 52)
            lines.append(f"  {'Plugin':<16} {'Avg':>7} {'P50':>7} {'P95':>7} {'Max':>7} {'Count':>7}")
            lines.append("  " + "-" * 52)
            for name, s in sorted(plugin_entries.items()):
                label = name.replace("plugin.", "")
                lines.append(
                    f"  {label:<16} {s['avg']:>6.1f}ms {s['p50']:>6.1f}ms "
                    f"{s['p95']:>6.1f}ms {s['max']:>6.1f}ms {s['count']:>6}"
                )

        lines.append("")

        # Latency
        lines.append("  Latency")
        lines.append("  " + "-" * 52)
        e2e = report.e2e
        fa = report.frame_age
        lines.append(f"  {'End-to-End':<16} {e2e['avg']:>6.1f}ms {e2e['p50']:>6.1f}ms "
                      f"{e2e['p95']:>6.1f}ms {e2e['max']:>6.1f}ms")
        lines.append(f"  {'Frame Age':<16} {fa['avg']:>6.1f}ms {fa['p50']:>6.1f}ms "
                      f"{fa['p95']:>6.1f}ms {fa['max']:>6.1f}ms")
        lines.append("")

        # Tick
        t = report.tick
        lines.append("  Tick")
        lines.append("  " + "-" * 52)
        lines.append(f"  Budget: {t['budget']}ms  Used: {t['avg']}ms avg  "
                      f"Overruns: {t['overruns']} ({t['overrun_pct']}%)")
        lines.append("")

        # Queues
        lines.append("  Queues")
        lines.append("  " + "-" * 52)
        for name, q in report.queues.items():
            label = name.upper().replace("_", " ")
            lines.append(f"  {label:<16} depth={q['depth']}  overwritten={q['overwritten']}  "
                          f"oldest={q['oldest_ms']}ms")

        lines.append("")

        # Verdicts
        lines.append("  Verdicts")
        lines.append("  " + "-" * 52)
        for v in report.verdicts:
            marker = "OK" if v == "ALL WITHIN BUDGET" else "!!"
            lines.append(f"  [{marker}] {v}")

        lines.append("=" * 56)
        return "\n".join(lines)

    # ── Logging ────────────────────────────────────────────────────

    def should_log(self) -> bool:
        now = time.perf_counter()
        if now - self._last_log_time >= self._log_interval:
            self._last_log_time = now
            return True
        return False

    def log_summary(self) -> str:
        snap = self.snapshot()
        lines = [
            "", "=" * 52, "  Vision Performance", "=" * 52,
            f"  FPS              {snap.tick_fps}",
            f"  Tick             {snap.tick_used_ms:.1f} ms / {snap.tick_budget_ms:.1f} ms"
            + (f"  OVR +{snap.tick_overrun_ms:.1f}" if snap.tick_overrun_ms > 0 else ""),
            "-" * 52,
        ]
        # Pipeline stages
        for name in ["camera", "yolo", "mediapipe", "vision_adapter", "render", "eventbus_flush"]:
            if name in snap.stages:
                s = snap.stages[name]
                label = name.upper().replace("_", " ")
                lines.append(f"  {label:<16} : {s['avg_ms']:>6.1f} ms  ({s['fps']:.0f} Hz)")
        # Plugin stages
        plugin_entries = {k: v for k, v in snap.stages.items() if k.startswith("plugin.")}
        if plugin_entries:
            lines.append("-" * 52)
            lines.append("  PLUGINS (Main Thread)")
            lines.append("-" * 52)
            for name, s in sorted(plugin_entries.items()):
                label = name.replace("plugin.", "")
                lines.append(f"  {label:<16} : {s['avg_ms']:>6.1f} ms  ({s['fps']:.0f} Hz)")
        lines.append("-" * 52)
        lines.append(f"  End2End Latency : {snap.e2e_latency_ms:>6.1f} ms")
        lines.append(f"  Frame Age       : {snap.frame_age_ms:>6.1f} ms")
        lines.append("")
        for name in ["frame_broker", "eventbus"]:
            if name in snap.queues:
                q = snap.queues[name]
                label = name.upper().replace("_", " ")
                parts = []
                if "depth" in q:
                    parts.append(f"depth={q['depth']}")
                if q.get("flush_ms", 0) > 0:
                    parts.append(f"flush={q['flush_ms']:.1f}ms")
                if q.get("oldest_ms", 0) > 0:
                    parts.append(f"oldest={q['oldest_ms']:.0f}ms")
                if q.get("overwritten", 0) > 0:
                    parts.append(f"overwritten={q['overwritten']}")
                lines.append(f"  {label:<16} : {'  '.join(parts)}")
        lines.append("=" * 52)
        summary = "\n".join(lines)
        logger.info(summary)
        return summary

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled


# Global singleton
profiler = Profiler()
