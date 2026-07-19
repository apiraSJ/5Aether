from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple
from datetime import datetime


@dataclass
class SpatialObject:
    id: str
    name: str
    label: str = ""
    location: str = ""
    position_3d: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    last_seen: str = ""
    status: str = "Visible"
    track_id: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.last_seen:
            self.last_seen = datetime.now().isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["position_3d"] = list(d["position_3d"])
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'SpatialObject':
        pos = data.get("position_3d", [0.0, 0.0, 0.0])
        if isinstance(pos, list):
            pos = tuple(pos)
        return cls(
            id=data["id"],
            name=data["name"],
            label=data.get("label", ""),
            location=data.get("location", ""),
            position_3d=pos,
            last_seen=data.get("last_seen", ""),
            status=data.get("status", "Visible"),
            track_id=data.get("track_id"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Task:
    id: str
    name: str
    type: str = "FIND"
    status: str = "PENDING"
    target_object_id: Optional[str] = None
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        return cls(
            id=data["id"],
            name=data["name"],
            type=data.get("type", "FIND"),
            status=data.get("status", "PENDING"),
            target_object_id=data.get("target_object_id"),
            created_at=data.get("created_at", ""),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class EventRecord:
    id: str
    type: str
    data: dict = field(default_factory=dict)
    source: str = ""
    timestamp: float = 0.0
