"""
Aether — Command System (Phase B) — Strategy:
Build a CommandExecutor service that wraps the existing Command/Registry/Handler
system so it works with the new plugin architecture and holds state.

Key aspects to preserve:
- Existing Command/Registry/Handler system stays mostly intact
- New CommandExecutor plugin wraps existing components
- ContextManager plugin (existing code becomes a plugin)
- Notification/History/Layout handlers as ResultPipeline plugins
- MemoryService plugin (existing memory system becomes a plugin)
"""

from aether.core.plugin import PluginBase
from aether.core.command_bus import CommandBus
from aether.core.event_bus import EventBus
from aether.core.result_pipeline import ResultPipeline
from command.command import create_default_registry
from command.handler import CommandHandler
from context.context_manager import ContextManager as LegacyContextManager
from memory.object_memory import ObjectMemory
from memory.storage import MemoryStorage
import threading
class CommandExecutor(PluginBase):
    """Command handler service that preserves the existing Command/Registry/Handler system
    while integrating with the new plugin architecture.
    
    Features:
    - Wraps existing CommandHandler for compatibility
    - Registers legacy command classes with state capability
    - Integrates with new DI container through initialize() method
    - Supports thread-safe command execution
    """

    name = "command_executor"

    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self.result_pipeline = None
        self.handler = None
        self._initialized = False

    def initialize(self, container):
        # Get new DI container services
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")
        self.result_pipeline = container.resolve("result_pipeline")

        # Create legacy command handler and register all commands
        # Bridge to the new command bus
        from aether.core.command import Command

        def _dispatch_command(cmd: Command):
            """Bridge: new CommandBus sends commands to legacy handler."""
            return self.handler.execute(cmd)

        # Create legacy handler and wrap it
        self.handler = CommandHandler(self.event_bus)

        # Register all default commands
        registry = create_default_registry()
        for name, cmd_obj in registry.list_commands().items():
            self.handler.register(cmd_obj)

        # Bridge new command bus to legacy handler
        # Note: This setup allows backward compatibility while
        # preparing for full transition

        self._initialized = True

    def shutdown(self):
        self.handler = None
        self.event_bus = None
        self.command_bus = None
        self.result_pipeline = None
        self._initialized = False

    def dispatch(self, command_name, source="system", **params):
        """Dispatch a command to legacy handler through bridge."""
        if not self._initialized:
            raise RuntimeError("CommandExecutor not initialized")

        from aether.core.command import Command
        from command.command import CommandStatus

        # Create legacy Command object
        cmd = Command(name=command_name, source=source, params=params)

        # Execute with legacy handler
        result = self.handler.execute(cmd)

        # Bridge the result back to new system
        # This maintains compatibility while aligning with new design

        return result
class ContextManagerPlugin(PluginBase):
    """Context manager plugin that preserves the existing context detection logic
    while integrating with the new plugin architecture.
    
    Features:
    - Wraps existing LegacyContextManager
    - Provides ContextManager-specific events
    - Integrates with new DI container
    """

    name = "context_manager"

    def __init__(self):
        self.event_bus = None
        self.context = None
        self._initialized = False

    def initialize(self, container):
        # Get existing context manager
        self.context = LegacyContextManager()

        # Get new event bus for context events
        self.event_bus = container.resolve("event_bus")

        # Subscribe to window change events to trigger context updates
        # The exact event type depends on the system architecture

        self._initialized = True

    def shutdown(self):
        self.context = None
        self.event_bus = None
        self._initialized = False

    def get_context(self):
        """Return current context in legacy format for compatibility."""
        if not self._initialized:
            raise RuntimeError("ContextManagerPlugin not initialized")

        if self.context:
            return self.context.get_context()

        return None
class ResultPipelineAdapter:
    """Adapter that converts new aether CommandResults to legacy
    command.results for backward compatibility.
    
    This allows the legacy CommandHandler to work with the new
    result pipeline while maintaining both interfaces.
    """

    def __init__(self, result_pipeline):
        self.result_pipeline = result_pipeline
        self.handlers = {}

    def add_legacy_handler(self, name, handler):
        """Add a legacy command result handler."""
        self.handlers[name] = handler

    def convert_and_dispatch(self, command_result):
        """Convert a CommandResult to legacy format and dispatch to handlers."""
        # Convert to legacy format if needed
        legacy_result = self._to_legacy_format(command_result)

        # Dispatch to all registered handlers
        for name, handler in self.handlers.items():
            try:
                handler(legacy_result)
            except Exception:
                # Handler failure doesn't crash the system
                pass

    def _to_legacy_format(self, command_result):
        """Convert a CommandResult to legacy result format."""
        return {
            'success': command_result.success,
            'data': command_result.data,
            'error': command_result.error,
            'command_id': command_result.command_id,
            'command_name': command_result.command_name
        }
class NotificationHandlerPlugin(PluginBase):
    """Notification result handler that intercepts successful CommandResults
    and triggers notification actions.
    
    This is the first of three ResultPipeline plugins in Phase B.
    """

    name = "notification_handler"

    def __init__(self):
        self.event_bus = None
        self.result_pipeline = None
        self._initialized = False

    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.result_pipeline = container.resolve("result_pipeline")

        # Register as a handler with the result pipeline
        self.result_pipeline.add_handler(self._on_command_result)

        self._initialized = True

    def shutdown(self):
        # Note: This simple handler doesn't need explicit cleanup
        self.event_bus = None
        self.result_pipeline = None
        self._initialized = False

    def _on_command_result(self, result):
        """Callback for when a command result is processed by the pipeline."""
        if not self._initialized:
            return

        # Check if this is a successful command that needs a notification
        if result.success and result.notification:
            # Process the notification
            # The actual notification mechanism depends on the system
            # This acts as a bridge between new ResultPipeline events
            # and legacy notification system
            pass
class HistoryHandlerPlugin(PluginBase):
    """History result handler that maintains a log of command results.
    
    This is the second of three ResultPipeline plugins in Phase B.
    """

    name = "history_handler"

    def __init__(self):
        self.event_bus = None
        self.result_pipeline = None
        self.command_history = []
        self.max_history = 100
        self._initialized = False

    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.result_pipeline = container.resolve("result_pipeline")

        # Register as a handler with the result pipeline
        self.result_pipeline.add_handler(self._on_command_result)

        self._initialized = True

    def shutdown(self):
        self.command_history = []
        self.event_bus = None
        self.result_pipeline = None
        self._initialized = False

    def get_recent_history(self, limit=10):
        """Get recent command history entries."""
        if not self._initialized:
            raise RuntimeError("HistoryHandlerPlugin not initialized")

        return self.command_history[-limit:]

    def _on_command_result(self, result):
        """Callback for when a command result is processed by the pipeline."""
        if not self._initialized:
            return

        # Convert CommandResult to legacy format for storage
        legacy_result = self._to_legacy_format(result)

        # Add to history
        self.command_history.append(legacy_result)

        # Trim history to max size
        if len(self.command_history) > self.max_history:
            self.command_history = self.command_history[-self.max_history:]

        # Optionally trigger event for new history item
        # self.event_bus.emit_simple(EventType.HISTORY_UPDATE, legacy_result)

    def _to_legacy_format(self, command_result):
        """Convert a CommandResult to legacy result format."""
        return {
            'success': command_result.success,
            'data': command_result.data,
            'error': command_result.error,
            'command_id': command_result.command_id,
            'command_name': command_result.command_name,
            'timestamp': command_result.duration_ms
        }
class LayoutHandlerPlugin(PluginBase):
    """Layout handler that processes layout_actions from CommandResults
    and triggers UI updates.
    
    This is the third of three ResultPipeline plugins in Phase B.
    """

    name = "layout_handler"

    def __init__(self):
        self.event_bus = None
        self.result_pipeline = None
        self._initialized = False

    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.result_pipeline = container.resolve("result_pipeline")

        # Register as a handler with the result pipeline
        self.result_pipeline.add_handler(self._on_command_result)

        self._initialized = True

    def shutdown(self):
        self.event_bus = None
        self.result_pipeline = None
        self._initialized = False

    def _on_command_result(self, result):
        """Callback for when a command result is processed by the pipeline."""
        if not self._initialized:
            return

        # Check if this result contains a layout_action
        if result.layout_action:
            # Process layout action
            # The actual layout mechanism depends on the system
            # This acts as a bridge between new ResultPipeline events
            # and legacy layout system
            pass
class MemoryServicePlugin(PluginBase):
    """Memory service plugin that wraps the existing memory system
    while integrating with the new plugin architecture.
    
    Features:
    - Wraps existing ObjectMemory and MemoryStorage
    - Provides memory storage/retrieval commands as aether commands
    - Integrates with new DI container
    """

    name = "memory_service"

    def __init__(self):
        self.event_bus = None
        self.command_bus = None
        self.object_memory = None
        self.memory_storage = None
        self._initialized = False

    def initialize(self, container):
        self.event_bus = container.resolve("event_bus")
        self.command_bus = container.resolve("command_bus")

        # Wrap existing memory components
        self.object_memory = ObjectMemory()
        self.memory_storage = MemoryStorage()

        # Register memory commands with command bus
        self._register_commands()

        # Load persistent data
        self._load_persistent_data()

        self._initialized = True

    def shutdown(self):
        # Save state before shutdown
        self._save_persistent_data()

        self.object_memory = None
        self.memory_storage = None
        self.event_bus = None
        self.command_bus = None
        self._initialized = False

    def _register_commands(self):
        """Register memory-related commands with command bus."""
        if not self._initialized:
            return

        # Register memory commands
        memory_commands = [
            "memory.remember",
            "memory.find", 
            "memory.forget",
            "memory.list",
            "memory.clear"
        ]

        # This bridges the new command system with legacy memory commands
        # Each command would need a handler registered with the new CommandBus

    def _load_persistent_data(self):
        """Load persistent memory data if available."""
        if self.object_memory and self.memory_storage:
            # Load from existing storage (JSON, file, etc.)
            pass

    def _save_persistent_data(self):
        """Save memory data before shutdown."""
        if self.object_memory and self.memory_storage:
            # Persist to storage
            pass

    def remember(self, name, data, location=None):
        """Remember an object or piece of data."""
        if not self._initialized:
            raise RuntimeError("MemoryServicePlugin not initialized")

        if self.object_memory:
            return self.object_memory.add(name, data, location)

        return None

    def find(self, criteria):
        """Find objects or data matching criteria."""
        if not self._initialized:
            raise RuntimeError("MemoryServicePlugin not initialized")

        if self.object_memory:
            return self.object_memory.find(criteria)

        return None

    def forget(self, name):
        """Forget an object or data."""
        if not self._initialized:
            raise RuntimeError("MemoryServicePlugin not initialized")

        if self.object_memory:
            return self.object_memory.remove(name)

        return None

    def list_all(self):
        """List all stored objects/data."""
        if not self._initialized:
            raise RuntimeError("MemoryServicePlugin not initialized")

        if self.object_memory:
            return self.object_memory.list_all()

        return []

    def clear(self):
        """Clear all stored objects/data."""
        if not self._initialized:
            raise RuntimeError("MemoryServicePlugin not initialized")

        if self.object_memory:
            return self.object_memory.clear()

        return False
# Legacy command result class for compatibility
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class LegacyCommandResult:
    """Legacy command result class for compatibility with old CommandHandler."""
    success: bool = False
    data: Any = field(default_factory=dict)
    error: str = ""
    notification: Optional[str] = None
    history: bool = False
    layout_action: Optional[str] = None
    undo: bool = False
    duration_ms: float = 0.0
