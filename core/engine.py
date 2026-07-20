from typing import Dict, Any, Optional
import logging
import threading
import time

from core.module import Module, ModuleManager
from core.event_bus import EventBus, EventType, Event, get_event_bus, set_event_bus


class AetherEngine:
    """Core engine - manages the Aether system lifecycle.
    
    This is the brain of Aether. It initializes modules, manages
    the event bus, and coordinates all system components.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.logger = logging.getLogger("Aether.Engine")
        
        # Core components
        self.event_bus = EventBus()
        set_event_bus(self.event_bus)
        
        self.module_manager = ModuleManager()
        
        # State
        self._running = False
        self._initialized = False
        self._start_time = 0.0
        
        # Register core event handlers
        self._register_core_handlers()
    
    def _register_core_handlers(self) -> None:
        """Register core system event handlers."""
        self.event_bus.subscribe(EventType.SYSTEM_SHUTDOWN, self._on_shutdown)
        self.event_bus.subscribe(EventType.SYSTEM_ERROR, self._on_error)
    
    def _on_shutdown(self, event: Event) -> None:
        self.logger.info("Shutdown event received")
        self.shutdown()
    
    def _on_error(self, event: Event) -> None:
        self.logger.error(f"System error: {event.data}")
    
    def register_module(self, module: Module) -> None:
        """Register a module with the engine."""
        self.module_manager.register(module)
    
    def initialize(self) -> bool:
        """Initialize the engine and all modules."""
        self.logger.info("Initializing Aether Engine...")
        
        try:
            # Initialize modules
            if not self.module_manager.initialize_all(self.config.get("modules", {})):
                self.logger.error("Module initialization failed")
                return False
            
            self._initialized = True
            self.logger.info("Aether Engine initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Engine initialization failed: {e}")
            return False
    
    def start(self) -> bool:
        """Start the engine and all modules."""
        if not self._initialized:
            self.logger.error("Engine not initialized")
            return False
        
        self.logger.info("Starting Aether Engine...")
        
        try:
            if not self.module_manager.start_all():
                self.logger.error("Module startup failed")
                return False
            
            self._running = True
            self._start_time = time.time()
            
            # Emit system start event
            self.event_bus.emit_simple(EventType.SYSTEM_START, {"uptime": 0})
            
            self.logger.info("Aether Engine started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Engine startup failed: {e}")
            return False
    
    def stop(self) -> None:
        """Stop the engine and all modules."""
        self.logger.info("Stopping Aether Engine...")
        self._running = False
        self.module_manager.stop_all()
        self.logger.info("Aether Engine stopped")
    
    def shutdown(self) -> None:
        """Shutdown the engine completely."""
        self.logger.info("Shutting down Aether Engine...")
        self.stop()
        self.module_manager.shutdown_all()
        self._initialized = False
        self.logger.info("Aether Engine shutdown complete")
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    @property
    def uptime(self) -> float:
        if self._start_time > 0:
            return time.time() - self._start_time
        return 0.0
    
    def get_status(self) -> Dict[str, Any]:
        """Get engine status."""
        return {
            "running": self._running,
            "initialized": self._initialized,
            "uptime": self.uptime,
            "modules": {
                name: {
                    "initialized": m.is_initialized,
                    "running": m.is_running
                }
                for name, m in self.module_manager.modules.items()
            }
        }


def create_engine(config: Dict[str, Any] = None) -> AetherEngine:
    """Factory function to create an Aether engine."""
    return AetherEngine(config)