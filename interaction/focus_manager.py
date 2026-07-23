"""
Focus Manager — Tracks which widget the cursor is hovering over

Provides:
- Widget registration with screen-space bounds
- Hit testing: cursor position → focused widget
- Focus/blur event dispatch
"""

import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass, field


@dataclass
class FocusableWidget:
    """A widget that can receive focus from the virtual cursor."""
    name: str
    bounds: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in screen coords
    on_focus: Optional[callable] = None
    on_blur: Optional[callable] = None
    on_select: Optional[callable] = None
    focused: bool = False


class FocusManager:
    """Tracks which widget the virtual cursor is hovering over."""

    def __init__(self):
        self.logger = logging.getLogger("Aether.FocusManager")
        self._widgets: List[FocusableWidget] = []
        self._focused: Optional[FocusableWidget] = None

    def register(self, widget: FocusableWidget):
        """Register a focusable widget."""
        self._widgets.append(widget)

    def unregister(self, name: str):
        """Unregister a widget by name."""
        self._widgets = [w for w in self._widgets if w.name != name]

    def update(self, cursor_x: float, cursor_y: float) -> Optional[str]:
        """Update focus based on cursor position. Returns focused widget name or None."""
        new_focused = None

        for widget in self._widgets:
            x1, y1, x2, y2 = widget.bounds
            if x1 <= cursor_x <= x2 and y1 <= cursor_y <= y2:
                new_focused = widget
                break

        # Handle focus change
        if new_focused != self._focused:
            if self._focused and self._focused.on_blur:
                self._focused.on_blur()
            self._focused = new_focused
            if self._focused and self._focused.on_focus:
                self._focused.on_focus()

        return self._focused.name if self._focused else None

    def select(self) -> Optional[str]:
        """Select the currently focused widget. Returns widget name or None."""
        if self._focused and self._focused.on_select:
            self._focused.on_select()
            return self._focused.name
        return None

    @property
    def focused_name(self) -> Optional[str]:
        return self._focused.name if self._focused else None

    @property
    def has_focus(self) -> bool:
        return self._focused is not None
