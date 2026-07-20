"""
Aether Brain - Main Entry Point
The brain runs without camera, responding to keyboard/mouse input.
"""
import sys
import logging
import argparse
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.engine import AetherEngine
from core.event_bus import EventBus, EventType, Event, get_event_bus
from core.module import Module, ModuleManager
from command.command import Command, CommandRegistry, create_default_registry
from command.handler import CommandHandler
from memory.storage import MemoryStorage
from context.context_manager import ContextManager
from interface.ui import run_aether_ui


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/aether.log")
        ]
    )
    # Create logs directory
    Path("logs").mkdir(exist_ok=True)


class AetherBrain:
    """Main Aether application - the brain without eyes."""
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.logger = logging.getLogger("Aether.Brain")
        
        # Core components
        self.engine = AetherEngine(config)
        self.event_bus = self.engine.event_bus
        self.memory = MemoryStorage()
        self.context_manager = ContextManager()
        self.command_registry = create_default_registry()
        self.command_handler = CommandHandler(self.event_bus)
        
        # UI reference
        self.ui = None
        
        # Register event handlers
        self._register_event_handlers()
        
        # Register core commands with engine
        self._register_core_modules()
    
    def _register_event_handlers(self):
        """Register core event handlers."""
        self.event_bus.subscribe(EventType.COMMAND_EXECUTE, self._on_command_execute)
        self.event_bus.subscribe(EventType.INPUT_HOTKEY, self._on_hotkey)
        self.event_bus.subscribe(EventType.CONTEXT_CHANGED, self._on_context_changed)
    
    def _register_core_modules(self):
        """Register modules with the engine."""
        # Modules would be registered here in full implementation
        pass
    
    def _on_command_execute(self, event: Event):
        """Handle command execution events."""
        cmd_data = event.data.get("command", {})
        if isinstance(cmd_data, dict):
            cmd = Command(**cmd_data)
            self.command_handler.execute(cmd)
    
    def _on_hotkey(self, event: Event):
        """Handle hotkey events from input."""
        hotkey = event.data.get("hotkey", "")
        
        # Default hotkeys
        hotkey_map = {
            "ctrl+space": ("open_ui", {}),
            "ctrl+1": ("switch_panel", {"panel": "system"}),
            "ctrl+2": ("switch_panel", {"panel": "developer"}),
            "ctrl+3": ("switch_panel", {"panel": "settings"}),
            "ctrl+d": ("set_mode", {"mode": "developer"}),
            "ctrl+p": ("set_mode", {"mode": "presentation"}),
            "ctrl+n": ("set_mode", {"mode": "normal"}),
        }
        
        if hotkey in hotkey_map:
            cmd_name, params = hotkey_map[hotkey]
            cmd = Command(name=cmd_name, source="keyboard", params=params)
            self.command_handler.execute(cmd)
    
    def _on_context_changed(self, event: Event):
        """Handle context changes."""
        mode = event.data.get("mode")
        if mode:
            self.context_manager.set_mode(mode)
    
    def initialize(self) -> bool:
        """Initialize the brain."""
        self.logger.info("Initializing Aether Brain...")
        return self.engine.initialize()
    
    def start(self) -> bool:
        """Start the brain."""
        self.logger.info("Starting Aether Brain...")
        return self.engine.start()
    
    def shutdown(self):
        """Shutdown the brain."""
        self.logger.info("Shutting down Aether Brain...")
        self.memory.save()
        self.engine.shutdown()
    
    def run_ui(self):
        """Run the UI (blocking)."""
        self.logger.info("Starting Aether UI...")
        run_aether_ui(self.context_manager, self.memory)


def run_interactive_mode(brain: AetherBrain):
    """Run interactive command-line mode for testing."""
    print("\n=== AETHER BRAIN - Interactive Mode ===")
    print("Commands: open_ui, close_ui, switch_panel, set_mode, get_status, quit")
    print("Hotkeys: ctrl+space (open UI), ctrl+1/2/3 (panels), ctrl+d/p/n (modes)")
    print("Type 'help' for commands, 'quit' to exit\n")
    
    while True:
        try:
            user_input = input("aether> ").strip().lower()
            
            if user_input in ("quit", "exit", "q"):
                break
            
            if user_input in ("help", "h", "?"):
                print("Available commands:")
                for name, desc in brain.command_registry.list_commands().items():
                    print(f"  {name} - {desc}")
                continue
            
            # Parse command
            parts = user_input.split()
            cmd_name = parts[0]
            params = {}
            
            # Simple param parsing: key=value
            for part in parts[1:]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k] = v
            
            cmd = Command(name=cmd_name, source="cli", params=params)
            result = brain.command_handler.execute(cmd)
            
            if result.success:
                print(f"  ✓ {result.data}")
            else:
                print(f"  ✗ {result.error}")
                
        except KeyboardInterrupt:
            break
        except EOFError:
            break
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\nGoodbye!")


def main():
    parser = argparse.ArgumentParser(description="Aether Brain - AI Spatial Assistant")
    parser.add_argument("--mode", choices=["ui", "cli", "headless"], default="ui",
                       help="Run mode: ui (GUI), cli (interactive), headless (background)")
    parser.add_argument("--log", default="INFO", help="Log level")
    parser.add_argument("--config", help="Config file path")
    args = parser.parse_args()
    
    setup_logging(args.log)
    
    logger = logging.getLogger("Aether.Main")
    logger.info("=" * 50)
    logger.info("Aether Brain Starting")
    logger.info("=" * 50)
    
    # Load config if provided
    config = {}
    if args.config:
        import json
        with open(args.config) as f:
            config = json.load(f)
    
    # Create brain
    brain = AetherBrain(config)
    
    # Initialize
    if not brain.initialize():
        logger.error("Failed to initialize brain")
        return 1
    
    # Start
    if not brain.start():
        logger.error("Failed to start brain")
        return 1
    
    try:
        if args.mode == "ui":
            # Run GUI (blocking)
            brain.run_ui()
        elif args.mode == "cli":
            # Run interactive CLI
            run_interactive_mode(brain)
        else:
            # Headless - just keep running
            logger.info("Running headless. Press Ctrl+C to stop.")
            import time
            while True:
                time.sleep(1)
                # Could do background tasks here
                
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1
    finally:
        brain.shutdown()
        logger.info("Aether Brain stopped")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())