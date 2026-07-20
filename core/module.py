from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging


class Module(ABC):
    """Base class for all Aether modules."""
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"Aether.{name}")
        self._initialized = False
        self._running = False
    
    @abstractmethod
    def initialize(self, config: Dict[str, Any] = None) -> bool:
        """Initialize the module with configuration."""
        pass
    
    @abstractmethod
    def start(self) -> bool:
        """Start the module."""
        pass
    
    @abstractmethod
    def stop(self) -> bool:
        """Stop the module."""
        pass
    
    @abstractmethod
    def shutdown(self) -> bool:
        """Shutdown and cleanup."""
        pass
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    @property
    def is_running(self) -> bool:
        return self._running


class ModuleManager:
    """Manages the lifecycle of all modules."""
    
    def __init__(self):
        self.modules: Dict[str, Module] = {}
        self.logger = logging.getLogger("Aether.ModuleManager")
    
    def register(self, module: Module) -> None:
        self.modules[module.name] = module
        self.logger.info(f"Registered module: {module.name}")
    
    def unregister(self, name: str) -> None:
        if name in self.modules:
            module = self.modules.pop(name)
            module.shutdown()
            self.logger.info(f"Unregistered module: {name}")
    
    def initialize_all(self, config: Dict[str, Any] = None) -> bool:
        all_ok = True
        for name, module in self.modules.items():
            try:
                module_config = config.get(name, {}) if config else {}
                if module.initialize(module_config):
                    module._initialized = True
                    self.logger.info(f"Initialized: {name}")
                else:
                    self.logger.error(f"Failed to initialize: {name}")
                    all_ok = False
            except Exception as e:
                self.logger.error(f"Error initializing {name}: {e}")
                all_ok = False
        return all_ok
    
    def start_all(self) -> bool:
        all_ok = True
        for name, module in self.modules.items():
            if module.is_initialized:
                try:
                    if module.start():
                        module._running = True
                        self.logger.info(f"Started: {name}")
                    else:
                        self.logger.error(f"Failed to start: {name}")
                        all_ok = False
                except Exception as e:
                    self.logger.error(f"Error starting {name}: {e}")
                    all_ok = False
        return all_ok
    
    def stop_all(self) -> None:
        for name, module in self.modules.items():
            if module.is_running:
                try:
                    module.stop()
                    module._running = False
                    self.logger.info(f"Stopped: {name}")
                except Exception as e:
                    self.logger.error(f"Error stopping {name}: {e}")
    
    def shutdown_all(self) -> None:
        for name in list(self.modules.keys()):
            self.unregister(name)
    
    def get_module(self, name: str) -> Optional[Module]:
        return self.modules.get(name)