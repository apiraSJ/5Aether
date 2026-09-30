"""Aether Panel implementations — view-only panels.

All panels in this package follow the view-only pattern:
- Dispatch commands through CommandBus
- Subscribe to events through EventBus
- Never access services, repositories, or managers directly
- Never mutate application state
"""

from aether.panels.placeholder_panel import PlaceholderPanel
from aether.panels.memory_panel import MemoryPanel

__all__ = [
    "PlaceholderPanel",
    "MemoryPanel",
]
