from dataclasses import dataclass
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


@dataclass(slots=True)
class Sample:
    time: float
    shot: int
    scores: list[float]
    raw_best_x: float
    confidence: float
    face_count: int
