from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VideoInfo:
    path: Path
    fps: float
    width: int
    height: int
    frames: int
    duration: float
    analysis_width: int
    analysis_height: int
    crop_width: int


@dataclass(frozen=True, slots=True)
class EntityObservation:
    track_id: int
    kind: str
    bbox: tuple[float, float, float, float]
    center: tuple[float, float]
    velocity: tuple[float, float]
    confidence: float
    age: int
    missed: int
    importance: float = 0.0


@dataclass(frozen=True, slots=True)
class InteractionEdge:
    source_id: int
    target_id: int
    relation: str
    strength: float
    confidence: float


@dataclass(slots=True)
class Sample:
    time: float
    shot: int
    scores: list[float]
    raw_best_x: float
    confidence: float
    face_count: int
    entities: list[EntityObservation] = field(default_factory=list)
    interactions: list[InteractionEdge] = field(default_factory=list)
