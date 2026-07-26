"""OverlayWidget — renders vision overlay on top of camera feed.

Draws bounding boxes, hand skeleton, cursor, and gesture indicators.
All data comes from OverlayModel — this widget never subscribes to events.

Optimizations:
  - QPainterPath cache per object (rebuild only when state changes)
  - QStaticText cache per label (pre-laid-out text)
  - QPainterPath cache per hand skeleton (rebuild only when landmarks change)
  - Stale cache cleanup (removed when objects/hands leave)
  - Size-change cache invalidation
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QBrush, QFont, QPainterPath, QStaticText,
)
from PySide6.QtWidgets import QWidget

from aether.ui.overlay_model import CursorState, GesturePhase

if TYPE_CHECKING:
    from aether.ui.overlay_model import OverlayModel

WHITE = QColor(255, 255, 255)
GRAY = QColor(191, 197, 210)
ACCENT = QColor(96, 165, 250)
WARNING = QColor(245, 158, 11)
CORNER_COLOR = QColor(255, 255, 255, 200)
CORNER_SELECTED = QColor(96, 165, 250, 220)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]

FONT_LABEL = QFont("Segoe UI Variable", 10, QFont.Light)
FONT_DIST = QFont("Segoe UI Variable", 9, QFont.Light)
FONT_GESTURE = QFont("Segoe UI Variable", 12, QFont.Light)
FONT_CONF = QFont("Segoe UI Variable", 9, QFont.Light)
FONT_NOTIF = QFont("Segoe UI Variable", 10, QFont.Light)


class _BoxCache:
    __slots__ = ("path", "label_text", "dist_text", "hash")

    def __init__(self) -> None:
        self.path: QPainterPath | None = None
        self.label_text: QStaticText | None = None
        self.dist_text: QStaticText | None = None
        self.hash: int = 0


class _HandCache:
    __slots__ = ("path", "hash")

    def __init__(self) -> None:
        self.path: QPainterPath | None = None
        self.hash: int = 0


class OverlayWidget(QWidget):
    """Transparent overlay that paints vision state from OverlayModel."""

    def __init__(self, model: OverlayModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background:transparent;")

        self._box_caches: dict[int, _BoxCache] = {}
        self._hand_caches: dict[str, _HandCache] = {}
        self._cursor_paths: dict[str, QPainterPath] = {}
        self._size_cache: tuple[int, int] = (0, 0)
        self._notif_bg: QPainterPath | None = None
        self._notif_bg_count: int = 0
        self._visible = True
        self._dirty_rects: list[tuple[float, float, float, float]] = []

        self._build_cursor_paths()

    def _build_cursor_paths(self) -> None:
        d = QPainterPath()
        d.addEllipse(QPointF(0, 0), 8, 8)
        self._cursor_paths["default"] = d

        h = QPainterPath()
        h.addEllipse(QPointF(0, 0), 10, 10)
        self._cursor_paths["hover_outer"] = h
        h_in = QPainterPath()
        h_in.addEllipse(QPointF(0, 0), 6, 6)
        self._cursor_paths["hover_inner"] = h_in

        p = QPainterPath()
        p.addEllipse(QPointF(0, 0), 12, 12)
        self._cursor_paths["pinch"] = p

    # ── Cache helpers ────────────────────────────────────────────────

    @staticmethod
    def _object_hash(obj) -> int:
        return hash((tuple(obj.box), obj.selected, obj.hovered, obj.name,
                      obj.confidence, obj.distance))

    def _ensure_box_cache(self, obj) -> _BoxCache | None:
        x1, y1, x2, y2 = obj.box
        if x2 <= x1 or y2 <= y1:
            return None

        cache = self._box_caches.get(obj.id)
        h = self._object_hash(obj)
        if cache is not None and cache.hash == h:
            return cache

        if cache is None:
            cache = _BoxCache()
            self._box_caches[obj.id] = cache

        cache.hash = h

        # Build QPainterPath for corner brackets
        path = QPainterPath()
        cl = min(20, (x2 - x1) // 4, (y2 - y1) // 4)
        # Top-left
        path.moveTo(x1, y1)
        path.lineTo(x1 + cl, y1)
        path.moveTo(x1, y1)
        path.lineTo(x1, y1 + cl)
        # Top-right
        path.moveTo(x2, y1)
        path.lineTo(x2 - cl, y1)
        path.moveTo(x2, y1)
        path.lineTo(x2, y1 + cl)
        # Bottom-left
        path.moveTo(x1, y2)
        path.lineTo(x1 + cl, y2)
        path.moveTo(x1, y2)
        path.lineTo(x1, y2 - cl)
        # Bottom-right
        path.moveTo(x2, y2)
        path.lineTo(x2 - cl, y2)
        path.moveTo(x2, y2)
        path.lineTo(x2, y2 - cl)
        cache.path = path

        # Label
        label = obj.name
        t = QStaticText(label)
        t.prepare()
        cache.label_text = t

        # Distance
        if obj.distance > 0:
            dt = QStaticText(f"{obj.distance:.1f}m")
            dt.prepare()
            cache.dist_text = dt
        else:
            cache.dist_text = None

        return cache

    def _hand_hash(self, hand) -> int:
        if not hand.landmarks:
            return 0
        return hash(tuple((lm.get("x", 0), lm.get("y", 0))
                          for lm in hand.landmarks[:21]))

    def _ensure_hand_cache(self, hand, w: int, h: int) -> _HandCache | None:
        landmarks = hand.landmarks
        if not landmarks or len(landmarks) < 21:
            return None

        cache = self._hand_caches.get(hand.label)
        hh = self._hand_hash(hand)
        if cache is not None and cache.hash == hh:
            return cache

        if cache is None:
            cache = _HandCache()
            self._hand_caches[hand.label] = cache

        cache.hash = hh

        path = QPainterPath()
        for i, j in HAND_CONNECTIONS:
            if i < len(landmarks) and j < len(landmarks):
                p1 = landmarks[i]
                p2 = landmarks[j]
                path.moveTo(p1["x"] * w, p1["y"] * h)
                path.lineTo(p2["x"] * w, p2["y"] * h)

        # Joint dots
        for lm in landmarks[:21]:
            px = lm["x"] * w
            py = lm["y"] * h
            path.addEllipse(QPointF(px, py), 1.5, 1.5)

        cache.path = path
        return cache

    # ── Paint ────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # Invalidate caches on resize
        if (w, h) != self._size_cache:
            self._box_caches.clear()
            self._hand_caches.clear()
            self._size_cache = (w, h)

        self._draw_objects(painter)
        self._draw_hands(painter, w, h)
        self._draw_cursor(painter, w, h)
        self._draw_gesture(painter, w, h)
        self._draw_notifications(painter, w, h)

        # Clean stale caches
        current_ids = {obj.id for obj in self._model.objects}
        stale = set(self._box_caches) - current_ids
        for sid in stale:
            del self._box_caches[sid]

        current_labels = {h.label for h in self._model.hands}
        stale_h = set(self._hand_caches) - current_labels
        for sid in stale_h:
            del self._hand_caches[sid]

        self._model.mark_clean()
        painter.end()

    def _draw_objects(self, painter: QPainter) -> None:
        normal_paths: list[QPainterPath] = []
        hover_paths: list[QPainterPath] = []
        selected_paths: list[QPainterPath] = []
        normal_texts: list[tuple[QStaticText, float, float]] = []
        hover_texts: list[tuple[QStaticText, float, float]] = []
        selected_texts: list[tuple[QStaticText, float, float]] = []
        normal_dists: list[tuple[QStaticText, float, float]] = []
        hover_dists: list[tuple[QStaticText, float, float]] = []
        selected_dists: list[tuple[QStaticText, float, float]] = []

        for obj in self._model.objects:
            cache = self._ensure_box_cache(obj)
            if cache is None:
                continue

            x1, y1, x2, y2 = obj.box

            if obj.selected:
                selected_paths.append(cache.path)
                selected_texts.append((cache.label_text, x1, y1 - 8))
                if cache.dist_text:
                    selected_dists.append((cache.dist_text, x1, y2 + 16))
            elif obj.hovered:
                hover_paths.append(cache.path)
                hover_texts.append((cache.label_text, x1, y1 - 8))
                if cache.dist_text:
                    hover_dists.append((cache.dist_text, x1, y2 + 16))
            else:
                normal_paths.append(cache.path)
                normal_texts.append((cache.label_text, x1, y1 - 8))
                if cache.dist_text:
                    normal_dists.append((cache.dist_text, x1, y2 + 16))

        # Batch normal objects
        if normal_paths or normal_texts:
            painter.setPen(QPen(CORNER_COLOR, 1.5))
            for p in normal_paths:
                painter.drawPath(p)
            painter.setFont(FONT_LABEL)
            painter.setPen(WHITE)
            for t, tx, ty in normal_texts:
                painter.drawStaticText(QPointF(tx, ty), t)
            if normal_dists:
                painter.setFont(FONT_DIST)
                painter.setPen(GRAY)
                for t, tx, ty in normal_dists:
                    painter.drawStaticText(QPointF(tx, ty), t)

        # Batch hovered objects
        if hover_paths or hover_texts:
            painter.setPen(QPen(WARNING, 1.5))
            for p in hover_paths:
                painter.drawPath(p)
            painter.setFont(FONT_LABEL)
            painter.setPen(WHITE)
            for t, tx, ty in hover_texts:
                painter.drawStaticText(QPointF(tx, ty), t)
            if hover_dists:
                painter.setFont(FONT_DIST)
                painter.setPen(GRAY)
                for t, tx, ty in hover_dists:
                    painter.drawStaticText(QPointF(tx, ty), t)

        # Batch selected objects
        if selected_paths or selected_texts:
            painter.setPen(QPen(CORNER_SELECTED, 2.0))
            for p in selected_paths:
                painter.drawPath(p)
            painter.setFont(FONT_LABEL)
            painter.setPen(WHITE)
            for t, tx, ty in selected_texts:
                painter.drawStaticText(QPointF(tx, ty), t)
            if selected_dists:
                painter.setFont(FONT_DIST)
                painter.setPen(GRAY)
                for t, tx, ty in selected_dists:
                    painter.drawStaticText(QPointF(tx, ty), t)

    def _draw_hands(self, painter: QPainter, w: int, h: int) -> None:
        pen = QPen(QColor(255, 255, 255, 120), 1.5)
        painter.setPen(pen)

        for hand in self._model.hands:
            cache = self._ensure_hand_cache(hand, w, h)
            if cache is None:
                continue
            painter.drawPath(cache.path)

    def _draw_cursor(self, painter: QPainter, w: int, h: int) -> None:
        cursor = self._model.cursor
        if not cursor.visible:
            return

        cx = int(cursor.x * w)
        cy = int(cursor.y * h)

        if cursor.state == CursorState.DEFAULT:
            path = self._cursor_paths.get("default")
            if path:
                p = QPainterPath(path)
                p.translate(cx, cy)
                painter.setPen(QPen(WHITE, 1.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(p)

        elif cursor.state == CursorState.HOVER:
            path = self._cursor_paths.get("hover_outer")
            if path:
                p = QPainterPath(path)
                p.translate(cx, cy)
                painter.setPen(QPen(ACCENT, 1.5))
                painter.setBrush(Qt.NoBrush)
                painter.drawPath(p)
            path = self._cursor_paths.get("hover_inner")
            if path:
                p = QPainterPath(path)
                p.translate(cx, cy)
                painter.drawPath(p)

        elif cursor.state == CursorState.PINCH:
            path = self._cursor_paths.get("pinch")
            if path:
                p = QPainterPath(path)
                p.translate(cx, cy)
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(ACCENT))
                painter.drawPath(p)

    def _draw_gesture(self, painter: QPainter, w: int, h: int) -> None:
        gesture = self._model.gesture
        if gesture.phase == GesturePhase.NONE:
            return

        cx = w // 2
        cy = h - 60

        name = gesture.name.replace("_", " ").title()
        painter.setFont(FONT_GESTURE)
        painter.setPen(WHITE)
        painter.drawText(cx - 50, cy, name)

        painter.setFont(FONT_CONF)
        painter.setPen(GRAY)
        painter.drawText(cx - 50, cy + 18, f"{gesture.confidence * 100:.0f}%")

        if gesture.phase == GesturePhase.HOLDING:
            progress = min(1.0, gesture.duration / 2.0)
            painter.setPen(QPen(ACCENT, 2.0))
            painter.setBrush(Qt.NoBrush)
            start_angle = 90 * 16
            span_angle = int(-360 * 16 * progress)
            painter.drawArc(cx + 40, cy - 10, 24, 24, start_angle, span_angle)

    def _draw_notifications(self, painter: QPainter, w: int, h: int) -> None:
        notifications = self._model.notifications
        for i, text in enumerate(notifications):
            painter.setFont(FONT_NOTIF)
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(text)
            rect_x = (w - text_w - 20) // 2
            rect_y = 40 + i * 30

            painter.setBrush(QBrush(QColor(0, 0, 0, 120)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect_x, rect_y, text_w + 20, 24, 6, 6)

            painter.setPen(WHITE)
            painter.drawText(rect_x + 10, rect_y + 17, text)

    def update(self) -> None:
        if self._model.dirty:
            super().update()

    def paint(self) -> None:
        pass

    # ── HUDManager integration ────────────────────────────────────────

    def is_visible(self) -> bool:
        """Check if widget is visible and should be rendered."""
        return self._visible and self.isVisible()

    def set_visible(self, visible: bool) -> None:
        """Set widget visibility."""
        self._visible = visible
        if not visible:
            self.hide()
        else:
            self.show()

    def get_dirty_rect(self) -> tuple[float, float, float, float] | None:
        """Get dirty region for partial repaint.
        Returns None for full repaint, or (x, y, w, h) for partial."""
        if self._dirty_rects:
            # Return union of all dirty rects
            x1 = min(r[0] for r in self._dirty_rects)
            y1 = min(r[1] for r in self._dirty_rects)
            x2 = max(r[0] + r[2] for r in self._dirty_rects)
            y2 = max(r[1] + r[3] for r in self._dirty_rects)
            return (x1, y1, x2 - x1, y2 - y1)
        return None

    def clear_dirty_rects(self) -> None:
        """Clear dirty rects after paint."""
        self._dirty_rects.clear()
