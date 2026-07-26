"""Core package for Aether architecture - new implementations only.

No legacy imports.

Contracts (frozen - do not modify without ADR):
    Command         — standardized unit of intent
    CommandResult   — standardized outcome of command execution
    EventType       — unified event type enum
    Event           — immutable event payload
    PointerEvent    — unified pointer input event
    IService        — base contract for all services
    PluginBase      — base contract for all plugins
    TickablePlugin  — base for plugins that participate in tick loop

Infrastructure:
    CommandBus      — queued command dispatch
    EventBus        — queued event pub/sub
    ResultPipeline  — fans out CommandResults to handlers
    ServiceContainer — DI container
    PluginLoader    — config-driven plugin loading
"""

from aether.core.command import Command
from aether.core.command_result import CommandResult
from aether.core.event_type import EventType
from aether.core.event_bus_v2 import Event, EventBus
from aether.core.pointer_event import (
    PointerEvent,
    PointerEventType,
    PointerButton,
    InputDevice,
)
from aether.core.service import IService, IStatefulService
from aether.core.plugin import PluginBase, TickablePlugin, PluginMetadata
from aether.core.command_bus import CommandBus
from aether.core.result_pipeline import ResultPipeline
from aether.core.service_container import ServiceContainer

__all__ = [
    # Contracts
    "Command",
    "CommandResult",
    "EventType",
    "Event",
    "PointerEvent",
    "PointerEventType",
    "PointerButton",
    "InputDevice",
    "IService",
    "IStatefulService",
    "PluginBase",
    "TickablePlugin",
    "PluginMetadata",
    # Infrastructure
    "CommandBus",
    "EventBus",
    "ResultPipeline",
    "ServiceContainer",
]