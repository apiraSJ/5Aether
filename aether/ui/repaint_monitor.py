"""RepaintMonitor — counts Qt repaints across a widget subtree.

Every QEvent.Paint that reaches any widget under the monitored window is
counted in the central profiler. The per-second repaint rate reveals
dirty-region effectiveness: a high rate while nothing visibly changes
indicates unnecessary full-window repaints.

Purely a measurement sidecar — consumes no events, conforms to no protocol.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject

from aether.core.profiler import profiler


class RepaintMonitor(QObject):
    """Event filter that counts repaints in a widget subtree."""

    def __init__(self, target: QObject) -> None:
        super().__init__(target)
        target.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Paint:
            profiler.record_repaint()
        return False
