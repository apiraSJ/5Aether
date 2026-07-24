# aether/core/reasoning_service.py
"""
ReasoningService — interprets MemoryService data to answer H1, H2, H3 questions.

This is where Aether becomes "smart" rather than just detecting.

H1: Persistent Memory > Session Memory (Recall Day 1,3,7)
H2: New client <5% core change, <100 LOC  
H3: Voice+Gesture > Voice only

Architecture:
Perception -> EventBus -> MemoryService -> ReasoningService -> UI

Design: Rule-based first, with LLM integration point for future scaling.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from aether.core.plugin import PluginBase
from aether.core.service_container import ServiceContainer
from aether.core.event_bus import EventBus

@dataclass
class SpatialObject:
    """Represents an object in persistent spatial memory."""
    id: str
    name: str
    position: Dict[str, Any]
    room: Optional[str] = None
    relations: List[Dict[str, Any]] = field(default_factory=list)
    last_seen: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)


class ReasoningService(PluginBase, name="reasoning"):
    """Interprets MemoryService data to answer spatial queries and
    violates H1/H2/H3 rules to prevent over-engineering.
    
    Uses the <context and <memory_services provided by DI.
    """
    
    def __init__(self, container: ServiceContainer = None):
        self.container = container
        self.memory = container.resolve("memory") if container else None
        self.event_bus = container.resolve("event_bus") if container else None
        self.logger = logging.getLogger("Aether.Reasoning")
        
    def initialize(self, container: ServiceContainer) -> None:
        """Initialize with MemoryService and EventBus."""
        if container is None:
            raise ValueError("ServiceContainer is required")
            
        self.container = container
        self.memory = container.resolve("memory") if container.has("memory") else None
        self.event_bus = container.resolve("event_bus") if container.has("event_bus") else None
        
        logger.debug("ReasoningService initialized")
    
    def where_is(self, name: str) -> Optional[str]:
        """Answer "where is <name>?" - H1 compliance (day recall).
        
        Returns formatted location string or None if not found.
        """
        try:
            obj = self.memory.where_is(name)
            if obj:
                # Format with spatial context
                location = f"{obj.position.get('room', 'unknown location')}"
                details = f"{obj.name} is in {location} at distance {obj.position.get('distance', 'unknown')}"
                if obj.last_seen:
                    days_ago = (datetime.now() - obj.last_seen).days
                    if days_ago > 0:
                        details += f" (recall: day {days_ago})"
                return details
        except Exception as e:
            logger.warning(f"where_is failed: {e}")
        return None
    
    def what_is_near(self, name: str) -> str:
        """Answer "what is near <name>?" - H3 feature (spatial relationships).
        
        Returns comma-separated list of nearby objects.
        """
        try:
            context = self.memory.what_is_near(name)
            if context and context.get("nearby_objects"):
                return f"{context['object_name']}'s nearby: {', '.join(context['nearby_objects'])}"
        except Exception as e:
            logger.warning(f"what_is_near failed: {e}")
        return "No nearby objects found."
    
    def remember(self, obj_data: Dict[str, Any]) -> Dict[str, Any]:
        """Remember object - H1 baseline (daily persistence).
        
        Returns success status and object ID.
        """
        try:
            if not obj_data.get("name"):
                return {"success": False, "reason": "Object must have a name"}
                
            obj_id = self.memory.remember(obj_data)
            return {"success": True, "object_id": obj_id}
        except Exception as e:
            logger.error(f"remember failed: {e}")
            return {"success": False, "reason": str(e)}
    
    def forget(self, name: str) -> Dict[str, Any]:
        """Forget object - Spatial memory management feature.
        
        Returns success status.
        """
        try:
            result = self.memory.forget(name)
            return {"success": True, "changed": result}
        except Exception as e:
            logger.error(f"forget failed: {e}")
            return {"success": False, "reason": str(e)}
    
    def query(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Process event and return Reasoning result.
        
        Safety checks to prevent H2/H3 violations.
        """
        try:
            question = event.get("data", {}).get("question")
            if not question:
                return {"result": "No question provided"}
            
            # Normalize question
            question_lower = question.lower()
            
            # Handle H1 questions (where/what)
            if question_lower.startswith("where is "):
                name = question[8:-1] if question.endswith("?") else question[8:]
                result = self.where_is(name)
                return {"result": result or "Not found"}
            
            elif question_lower.startswith("what is near "):
                name = question[11:-1] if question.endswith("?") else question[11:]
                result = self.what_is_near(name)
                return {"result": result}
            
            elif "remember" in question_lower:
                # Simple remember parsing
                words = question.split()
                for i, word in enumerate(words):
                    if word.lower() in ["remember", "remember that"]:
                        desc = " ".join(words[i+2:]) if i+2 < len(words) else ""
                        obj_data = {
                            "name": desc.split(" ")[0] if desc else "unknown",
                            "description": desc,
                            "timestamp": datetime.now().isoformat()
                        }
                        result = self.remember(obj_data)
                        return {"result": f"Memory saved: {result}"} if result["success"] else {"result": f"Memory save failed: {result.get('reason')}"}
            
            elif "forget" in question_lower:
                words = question.split()
                for i, word in enumerate(words):
                    if word.lower() == "forget":
                        name = words[i+1] if i+1 < len(words) else "unknown"
                        result = self.forget(name)
                        return {"result": f"Forget: {result['changed']}" if result["success"] else {"result": f"Forget failed: {result.get('reason')}"}
            
            return {"result": f"Don't understand: {question}"}
            
        except Exception as e:
            logger.error(f"query failed: {e}")
            return {"result": f"Error processing: {str(e)}"}
    
    def get_help(self) -> str:
        """Return help information about ReasoningService capabilities."""
        return (
            "ReasoningService handles:\n"
            "- where_is(name): Answer 'where is name?' (H1 compliance)\"
            "- what_is_near(name): Answer 'what is near name?' (spatial relations)\"
            "- remember(object): Save object to persistent memory (H1 baseline)\"
            "- forget(name): Remove object from memory (spatial management)\"
            "- query(event): Process arbitrary questions with safety checks\"
            "\nRules: Reuse existing MemoryService, never modify core/ unless absolutely necessary."
        )
