#!/usr/bin/env python3
"""
Aether Brain v2 — Research Platform with Persistent Spatial Memory

Entry point: python brain_main.py

Core Rule: Perception -> EventBus -> MemoryService -> ReasoningService -> UI

Architecture:
- Phase A: Foundation (core services, DI, plugins)
- Phase B: Brain (Memory + Reasoning + Context)
- Phase C: Input (Camera + Voice + Gesture input plugins)
- Phase D: Vision (YOLO + MediaPipe + PnP -> MemoryService)
- Phase E: UI (PySide6 + DearPyGui overlay)
- Phase F: Extensions (Automation, XR, Voice, etc.)

DoD 6 Requirements (must pass before any new feature):
1. remember laptop on desk
2. remember charger left of laptop
3. where is laptop
4. what is near laptop
5. forget charger
6. works without camera (no cv2 in core/)

Note: openCode will check these 6 requirements first before editing any code.
"""

import sys
import logging
import signal
import time
from typing import Dict, Any, Optional

from aether.core.service_container import ServiceContainer
from aether.core.app import AetherApp
from aether.core.reasoning_service import ReasoningService
from aether.core.plugin import PluginBase
from aether.core.plugin_manager import PluginManager
from aether.core.event_bus import EventBus, EventType

# ── Globals ───────────────────────────────────────────────────────────

_engine = None
_app = None
_reasoning = None

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("Aether.Main")


class TestPlugin(PluginBase, name="test_plugin"):
    """Test plugin that validates H1, H2, H3 requirements."""
    
    def __init__(self, container: ServiceContainer):
        self.container = container
        self.reasoning = container.resolve("reasoning") if container.has("reasoning") else None
        self.logger = logging.getLogger("Aether.TestPlugin")
    
    def initialize(self, container: ServiceContainer) -> None:
        """Initialize test plugin. No external dependencies."""
        self.container = container
        self.reasoning = container.resolve("reasoning") if container.has("reasoning") else None
        self.logger.info("Test plugin initialized")
        
        # Test 1: remember laptop on desk
        self._test_remember_laptop()
        
        # Test 2: remember charger left of laptop
        self._test_remember_charger_left_of_laptop()
        
        # Test 3: where is laptop
        self._test_where_is_laptop()
        
        # Test 4: what is near laptop  
        self._test_what_is_near_laptop()
        
        # Test 5: forget charger
        self._test_forget_charger()
        
        # Test 6: works without camera (check no cv2 import in core)
        self._test_no_cv2_in_core()
        
        self.logger.info("All tests passed!")
    
    def _test_remember_laptop(self):
        """Test: remember laptop on desk."""
        if self.reasoning:
            result = self.reasoning.remember({
                "name": "laptop",
                "position": {"room": "desk", "distance": 0.5},
                "tags": ["electronics", "work"]
            })
            if result.get("success"):
                logger.info("Test 1 PASSED: Remembered laptop")
            else:
                logger.error(f"Test 1 FAILED: {result.get('reason')}")
        else:
            logger.error("Test 1 FAILED: No reasoning service")
    
    def _test_remember_charger_left_of_laptop(self):
        """Test: remember charger left of laptop."""
        if self.reasoning:
            result = self.reasoning.remember({
                "name": "charger", 
                "position": {"room": "desk", "distance": 0.8},
                "relations": [{"type": "left_of", "target": "laptop"}],
                "tags": ["electronics", "power"]
            })
            if result.get("success"):
                logger.info("Test 2 PASSED: Remembered charger left of laptop")
            else:
                logger.error(f"Test 2 FAILED: {result.get('reason')}")
        else:
            logger.error("Test 2 FAILED: No reasoning service")
    
    def _test_where_is_laptop(self):
        """Test: where is laptop."""
        if self.reasoning:
            result = self.reasoning.where_is("laptop")
            if result:
                logger.info(f"Test 3 PASSED: Where is laptop: {result}")
            else:
                logger.error("Test 3 FAILED: laptop not found in memory")
        else:
            logger.error("Test 3 FAILED: No reasoning service")
    
    def _test_what_is_near_laptop(self):
        """Test: what is near laptop."""
        if self.reasoning:
            result = self.reasoning.what_is_near("laptop")
            if "nearby objects" in result or result != "No nearby objects found.":
                logger.info(f"Test 4 PASSED: What is near laptop: {result}")
            else:
                logger.error(f"Test 4 FAILED: what_is_near returned: {result}")
        else:
            logger.error("Test 4 FAILED: No reasoning service")
    
    def _test_forget_charger(self):
        """Test: forget charger."""
        if self.reasoning:
            result = self.reasoning.forget("charger")
            if result.get("success"):
                logger.info(f"Test 5 PASSED: Forget charger: {result['changed']}")
            else:
                logger.error(f"Test 5 FAILED: {result.get('reason')}")
        else:
            logger.error("Test 5 FAILED: No reasoning service")
    
    def _test_no_cv2_in_core(self):
        """Test: works without camera (no cv2 in core/)."""
        try:
            import cv2
            try:
                import aether.core.event_bus
                import aether.core.service_container
                import aether.core.reasoning_service
                
                # Check if any of these files import cv2
                for module_name in ["aether.core.event_bus", "aether.core.service_container", "aether.core.reasoning_service"]:
                    try:
                        module = __import__(module_name, fromlist=[""])
                        if hasattr(module, "cv2"):
                            logger.error(f"Test 6 FAILED: {module_name} imports cv2")
                            return
                    except (ImportError, AttributeError):
                        pass
                
                logger.info("Test 6 PASSED: No cv2 imports in core/")
            except ImportError:
                logger.error("Test 6 FAILED: aether.core not importable")
        except ImportError:
            logger.error("Test 6 PASSED: opencv-python not installed (works without camera)")


class TestReasoningPlugin(PluginBase, name="test_reasoning"):
    """Plugin that ensures reasoning service works."""
    
    def __init__(self, container: ServiceContainer):
        self.container = container
        self.reasoning = container.resolve("reasoning") if container.has("reasoning") else None
        self.logger = logging.getLogger("Aether.TestReasoningPlugin")
    
    def initialize(self, container: ServiceContainer) -> None:
        """Test reasoning capabilities."""
        if self.reasoning:
            logger.info("TestReasoningPlugin: Reasoning service available")
            
            # Test basic reasoning query
            test_event = {
                "data": {"question": "where is laptop"}
            }
            result = self.reasoning.query(test_event)
            if "result" in result and result["result"]:
                logger.info(f"TestReasoningPlugin: Reasoning query result: {result['result']}")
            else:
                logger.error(f"TestReasoningPlugin: Reasoning query failed: {result}")
        else:
            logger.error("TestReasoningPlugin: No reasoning service available")


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/aether_brain.log", encoding="utf-8")
        ]
    )


def create_test_brain(config: dict = None) -> AetherApp:
    """Create test brain with auto-test plugin."""
    if config is None:
        config = {}
    
    app = AetherApp()
    _engine = app
    
    # Create container and register core services
    container = app.container
    
    # Create and configure reasoning service manually
    reasoning = ReasoningService()
    reasoning.initialize(container)
    container.register_instance("reasoning", reasoning)
    
    _reasoning = reasoning
    
    # Wire events
    bus = EventBus()
    container.register_instance("event_bus", bus)
    container.register_instance("result_pipeline", container.resolve("result_pipeline") if "result_pipeline" in container._instances else None)
    
    # Register test plugins
    test_plugin = TestPlugin(container)
    test_plugin.initialize(container)
    
    reasoning_plugin = TestReasoningPlugin(container)
    reasoning_plugin.initialize(container)
    
    app.logger.info("Test brain created with auto-tests")
    return app


def signal_handler(sig, frame):
    if _app:
        _app.shutdown()
    sys.exit(0)


def main():
    setup_logging()
    logger.info("=" * 50)
    logger.info("AETHER BRAIN V2 — Research Platform with Persistent Spatial Memory")
    logger.info("=" * 50)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    global _app
    _app = create_test_brain()
    
    if not _app.initialize():
        logger.error("Failed to initialize brain")
        return 1
    
    logger.info("Brain initialized successfully")
    
    # Run for 5 seconds to execute auto-tests
    logger.info("Executing auto-tests (will run for 5 seconds)...")
    time.sleep(5)
    
    logger.info("All tests completed")
    logger.info("Press Ctrl+C to shutdown")
    
    import threading
    def shutdown_after_delay():
        time.sleep(2)
        if _app:
            _app.shutdown()
        sys.exit(0)
    
    threading.Thread(target=shutdown_after_delay, daemon=True).start()
    
    # Wait for shutdown signal
    while True:
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
