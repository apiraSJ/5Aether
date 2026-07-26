"""PerformanceHUD — developer-mode performance metrics overlay.

Shows real-time profiling data from the central Profiler:
  - FPS, Tick budget/used/overrun
  - Camera, YOLO, MediaPipe, VisionAdapter, Render, EventBus flush times
  - End-to-End Latency, Frame Age
  - Event Queue depth/oldest age, Frame Broker overwritten
  - Adaptive Scheduler: YOLO/MediaPipe/Vision rates, layer intervals, skip flags, CPU load

Conforms to HUDManager Widget Protocol: update() + paint().
Hidden by default. Toggle with `PerformanceHUD.toggle()`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import QWidget

from aether.core.profiler import profiler
from aether.core.adaptive_scheduler import adaptive_scheduler

BG = QColor(0, 0, 0, 160)
WHITE = QColor(255, 255, 255)
GRAY = QColor(191, 197, 210)
ACCENT = QColor(96, 165, 250)
GREEN = QColor(34, 197, 94)
YELLOW = QColor(245, 158, 11)
RED = QColor(239, 68, 68)


def _color_for_ms(ms: float) -> QColor:
    if ms < 10:
        return GREEN
    if ms < 50:
        return YELLOW
    return RED


def _color_for_latency(ms: float) -> QColor:
    if ms < 33:
        return GREEN
    if ms < 80:
        return YELLOW
    return RED


def _color_for_overrun(ms: float) -> QColor:
    if ms <= 0:
        return GREEN
    if ms < 5:
        return YELLOW
    return RED


def _color_for_hz(hz: float, target: float) -> QColor:
    if hz >= target * 0.8:
        return GREEN
    if hz >= target * 0.5:
        return YELLOW
    return RED


def _color_for_bool(val: bool) -> QColor:
    return RED if val else GREEN


class PerformanceHUD(QWidget):
    """Developer-mode performance metrics overlay.

    Reads from the global `profiler` singleton and `adaptive_scheduler`.
    No EventBus subscription. No model mutation.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedWidth(300)
        self._visible = True
        self.hide()  # Hidden by default

        self._font = QFont("Consolas", 9)
        self._font_bold = QFont("Consolas", 9, QFont.Bold)
        self._lines: list[tuple[str, QColor, str]] = []

    def update(self) -> None:
        """Read profiler snapshot and adaptive scheduler state, build display lines."""
        snap = profiler.snapshot()
        sched_metrics = adaptive_scheduler.get_metrics()
        self._lines = []

        # ── Header + Tick ──────────────────────────────────────
        self._lines.append(("  AETHER PERF", WHITE, ""))
        overrun_str = ""
        if snap.tick_overrun_ms > 0:
            overrun_str = f"  OVR +{snap.tick_overrun_ms:.0f}"
        self._lines.append((
            "  Tick",
            _color_for_overrun(snap.tick_overrun_ms),
            f"{snap.tick_used_ms:.1f}/{snap.tick_budget_ms:.0f}ms {snap.tick_fps:.0f}Hz{overrun_str}",
        ))

        self._lines.append(("", WHITE, ""))

        # ── Pipeline Timing ────────────────────────────────────
        stages = [
            ("camera", "Camera"),
            ("yolo", "YOLO"),
            ("mediapipe", "MediaPipe"),
            ("vision_adapter", "Vision"),
            ("render", "Render"),
            ("eventbus_flush", "Flush"),
        ]

        for key, label in stages:
            if key in snap.stages:
                s = snap.stages[key]
                avg = s["avg_ms"]
                fps = s["fps"]
                color = _color_for_ms(avg)
                self._lines.append((f"  {label:<12}", color, f"{avg:>5.1f} ms {fps:>4.0f}Hz"))

        # ── Adaptive Rates ─────────────────────────────────────
        self._lines.append(("", WHITE, ""))
        self._lines.append(("  ADAPTIVE RATES", ACCENT, ""))

        yolo_hz = sched_metrics.get("yolo_hz", 0)
        mp_hz = sched_metrics.get("mediapipe_hz", 0)
        vis_hz = sched_metrics.get("vision_hz", 0)
        cpu_load = sched_metrics.get("cpu_load", 0)

        self._lines.append((
            "  YOLO",
            _color_for_hz(yolo_hz, 15),
            f"{yolo_hz:.1f}Hz",
        ))
        self._lines.append((
            "  MediaPipe",
            _color_for_hz(mp_hz, 20),
            f"{mp_hz:.1f}Hz",
        ))
        self._lines.append((
            "  Vision",
            _color_for_hz(vis_hz, 10),
            f"{vis_hz:.1f}Hz",
        ))
        self._lines.append((
            "  CPU Load",
            _color_for_ms(cpu_load / 10),  # scale
            f"{cpu_load:.0f}%",
        ))

        # ── Skip Flags ─────────────────────────────────────────
        skip_yolo = sched_metrics.get("skip_yolo", False)
        skip_mp = sched_metrics.get("skip_mediapipe", False)
        skip_vis = sched_metrics.get("skip_vision", False)

        self._lines.append((
            "  Skip YOLO",
            _color_for_bool(skip_yolo),
            "YES" if skip_yolo else "no",
        ))
        self._lines.append((
            "  Skip MP",
            _color_for_bool(skip_mp),
            "YES" if skip_mp else "no",
        ))
        self._lines.append((
            "  Skip Vis",
            _color_for_bool(skip_vis),
            "YES" if skip_vis else "no",
        ))

        # ── Layer Intervals ────────────────────────────────────
        layer2_hz = sched_metrics.get("layer_2_hz", 0)
        layer3_hz = sched_metrics.get("layer_3_hz", 0)
        self._lines.append((
            "  Layer2",
            GRAY,
            f"{layer2_hz:.1f}Hz",
        ))
        self._lines.append((
            "  Layer3",
            GRAY,
            f"{layer3_hz:.1f}Hz",
        ))

        self._lines.append(("", WHITE, ""))

        # ── Latency Metrics ────────────────────────────────────
        self._lines.append((
            "  End2End",
            _color_for_latency(snap.e2e_latency_ms),
            f"{snap.e2e_latency_ms:.0f} ms",
        ))
        self._lines.append((
            "  Frame Age",
            _color_for_latency(snap.frame_age_ms),
            f"{snap.frame_age_ms:.0f} ms",
        ))

        self._lines.append(("", WHITE, ""))

        # ── Queue Metrics ──────────────────────────────────────
        if "frame_broker" in snap.queues:
            q = snap.queues["frame_broker"]
            overwritten = q.get("overwritten", 0)
            self._lines.append((
                "  FrameBroker",
                GRAY,
                f"drop={overwritten}",
            ))

        if "eventbus" in snap.queues:
            q = snap.queues["eventbus"]
            queued = q.get("queued", 0)
            oldest = q.get("oldest_ms", 0)
            self._lines.append((
                "  EventBus",
                GRAY,
                f"q={queued} oldest={oldest:.0f}ms",
            ))

        super().update()

    def paint(self) -> None:
        """Qt handles painting via paintEvent."""
        pass

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = len(self._lines) * 16 + 12

        # Background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(BG))
        painter.drawRoundedRect(0, 0, w, h, 6, 6)

        # Lines
        y = 16
        for label, color, value in self._lines:
            if not label and not value:
                y += 6
                continue

            painter.setFont(self._font_bold)
            painter.setPen(WHITE)
            painter.drawText(8, y, label)

            painter.setFont(self._font)
            painter.setPen(color)
            painter.drawText(130, y, value)

            y += 16

        painter.end()

    def toggle(self) -> None:
        """Toggle visibility."""
        if self.isVisible():
            self.hide()
        else:
            self.show()

    def is_visible(self) -> bool:
        return self._visible and super().isVisible()

    def get_dirty_rect(self) -> tuple[float, float, float, float] | None:
        return None