"""
Phase A — Foundational architecture (already complete)

Contains the core DI container and runtime orchestration:
- ServiceContainer (IService ABC)
- EventBus (4 categories: System/UI/Data/Command)
- CommandBus (sync/async dispatch)
- ResultPipeline (logging + plugins)
- PluginBase (common contract)
- PluginLoader (config-driven)
"""

from .app import AetherApp
from .core.plugin_loader import PluginLoader
from .core.service_container import ServiceContainer
from .core.command import Command
from .core.command_result import CommandResult
from .core.command_bus import CommandBus
from .core.event_bus import EventBus
from .core.result_pipeline import ResultPipeline
from .core.plugin import PluginBase
from .config.loader import ConfigLoader
from .plugins.system_info_plugin import SystemInfoPlugin

__all__ = [
    "AetherApp",
    "PluginLoader", 
    "ServiceContainer",
    "Command",
    "CommandResult",
    "CommandBus",
    "EventBus",
    "ResultPipeline",
    "PluginBase",
    "ConfigLoader",
    "SystemInfoPlugin",
]
