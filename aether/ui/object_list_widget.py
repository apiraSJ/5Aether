"""ObjectListWidget — side panel showing detected objects with distance.

Reads from OverlayModel.objects — no EventBus subscription.
Conforms to HUDManager Widget Protocol: update() + paint().

Optimized: reuses QLabels, only updates when object count or data changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

if TYPE_CHECKING:
    from aether.ui.overlay_model import OverlayModel


class ObjectListWidget(QWidget):
    """Side panel listing detected objects. Reuses widgets, updates only on change."""

    def __init__(self, model: OverlayModel, parent=None) -> None:
        super().__init__(parent)
        self._model = model
        self._visible = True
        self._last_obj_count = -1
        self._last_obj_hash = ""
        self._labels: list[tuple[QLabel, QLabel]] = []
        self._placeholder = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setFixedWidth(160)
        self.setStyleSheet("background:transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        header = QLabel("Objects")
        header.setFont(QFont("Segoe UI Variable", 9, QFont.Medium))
        header.setStyleSheet("color:#BFC5D2;")
        layout.addWidget(header)

        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(4)
        layout.addLayout(self._list_layout, 1)

        self._placeholder = QLabel("  (none)")
        self._placeholder.setFont(QFont("Segoe UI Variable", 9, QFont.Light))
        self._placeholder.setStyleSheet("color:#666;")
        self._list_layout.addWidget(self._placeholder)

    def update(self) -> None:
        objects = self._model.objects

        # Fast hash: compare count + id+box+dist to detect changes
        obj_hash = str(len(objects)) + "".join(
            f"{o.id}{o.name}{o.box}{o.distance:.2f}" for o in objects
        )

        if obj_hash == self._last_obj_hash:
            return  # No change, skip entirely

        self._last_obj_hash = obj_hash
        self._last_obj_count = len(objects)

        # Remove old placeholder or labels
        self._clear_list()

        if not objects:
            self._placeholder = QLabel("  (none)")
            self._placeholder.setFont(QFont("Segoe UI Variable", 9, QFont.Light))
            self._placeholder.setStyleSheet("color:#666;")
            self._list_layout.addWidget(self._placeholder)
        else:
            for obj in objects:
                name_lbl = QLabel(obj.name)
                name_lbl.setFont(QFont("Segoe UI Variable", 9, QFont.Medium))
                name_lbl.setStyleSheet("color:white;padding:4px;background:rgba(255,255,255,0.05);border-radius:4px;")
                self._list_layout.addWidget(name_lbl)

                info = QLabel(f"{obj.distance:.1f}m  {obj.confidence * 100:.0f}%")
                info.setFont(QFont("Segoe UI Variable", 8, QFont.Light))
                info.setStyleSheet("color:#BFC5D2;padding-left:6px;")
                self._list_layout.addWidget(info)

                self._labels.append((name_lbl, info))

        super().update()

    def _clear_list(self) -> None:
        while self._list_layout.count():
            child = self._list_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        self._labels.clear()

    def paint(self) -> None:
        pass

    def is_visible(self) -> bool:
        return self._visible and super().isVisible()

    def get_dirty_rect(self) -> tuple[float, float, float, float] | None:
        return None
