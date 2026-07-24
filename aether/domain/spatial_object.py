"""SpatialObject — an entity with physical position and relationships.

This is the core domain model for spatial memory. It represents any
object that exists at a location and can be related to other objects.

Design notes:
- frozen=True: once created, the object is immutable in memory.
  Modifications create a new instance (snapshot semantics).
- Relations are stored as a list of SpatialRelation, NOT nested objects.
  This keeps the graph flat and queryable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SpatialRelation:
    """A directed relationship between two spatial objects.

    Examples:
        SpatialRelation(type="left_of", target_id="obj_charger")
        SpatialRelation(type="near", target_id="obj_monitor", distance=0.3)
        SpatialRelation(type="on_top_of", target_id="obj_desk")
    """

    type: str
    target_id: str
    distance: Optional[float] = None
    confidence: float = 1.0
    source: str = "perception"  # "perception" | "user_input" | "inferred"


@dataclass(frozen=True)
class SpatialObject:
    """An entity that exists at a physical location.

    Lifecycle:
        1. Created by perception (YOLO + PnP) or user command ("remember laptop on desk")
        2. Stored in IMemoryRepository
        3. Recalled by IMemoryService
        4. Reasoned about by IReasoningService

    Example:
        obj = SpatialObject(
            name="laptop",
            position={"room": "desk", "x": 0.5, "y": 0.2, "z": 0.8},
            relations=[
                SpatialRelation(type="left_of", target_id="obj_charger"),
                SpatialRelation(type="on_top_of", target_id="obj_desk"),
            ],
            tags=["electronics", "work"],
        )
    """

    id: str = field(default_factory=lambda: f"obj_{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    position: Dict[str, Any] = field(default_factory=dict)
    relations: List[SpatialRelation] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_update(self, **kwargs) -> SpatialObject:
        """Return a new SpatialObject with updated fields.

        Since the dataclass is frozen, we create a new instance.
        This enforces snapshot semantics: old references stay valid.
        """
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "position": dict(self.position),
            "relations": list(self.relations),
            "tags": list(self.tags),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }
        data.update(kwargs)
        return SpatialObject(**data)

    def add_relation(self, relation: SpatialRelation) -> SpatialObject:
        """Return new object with added relation."""
        return self.with_update(relations=self.relations + [relation])

    def remove_relation(self, target_id: str) -> SpatialObject:
        """Return new object with relation to target removed."""
        return self.with_update(
            relations=[r for r in self.relations if r.target_id != target_id]
        )

    def has_relation(self, relation_type: str, target_id: str) -> bool:
        """Check if this object has a specific relation."""
        return any(
            r.type == relation_type and r.target_id == target_id
            for r in self.relations
        )

    def related_objects(self, relation_type: Optional[str] = None) -> List[str]:
        """Get IDs of related objects, optionally filtered by type."""
        if relation_type:
            return [r.target_id for r in self.relations if r.type == relation_type]
        return [r.target_id for r in self.relations]
