"""
ClipperX 0.3 - Data models

Plain dataclasses shared across the reframe pipeline. No behaviour here, just
typed containers so the stages (detector -> speaker -> planner -> renderer) have
a clear contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


@dataclass
class VideoMeta:
    """Basic information about the source video."""
    width: int
    height: int
    fps: float
    total_frames: int
    duration: float
    path: str


@dataclass
class Detection:
    """A single face detected in a single frame."""
    cx: float          # face center x (pixels, source coords)
    cy: float          # face center y
    w: float           # face bbox width
    h: float           # face bbox height
    mouth_open: float  # inner-lip vertical gap / face height (0 = closed)


@dataclass
class FrameDetections:
    """All faces detected in one frame."""
    frame_num: int
    faces: List[Detection] = field(default_factory=list)


class FramingKind(str, Enum):
    FOCUS = "focus"    # single crop following one subject (or held when absent)
    SPLIT = "split"    # two stacked crops (top/bottom) showing two people


class SceneMode(str, Enum):
    """The scene-level layout decision (L2). Committed via asymmetric hysteresis so it
    doesn't flicker; drives which framing behaviour runs. See DESIGN.md sections 2 & 4."""
    HOLD = "hold"      # nobody to follow: hold framing + drift toward motion
    SOLO = "solo"      # one subject: calm follow
    DUAL = "dual"      # two subjects: punch-in on active speaker, or split on joint moment
    GROUP = "group"    # 3+ subjects: dominant-speaker focus for now (centroid-fit = roadmap #6)


@dataclass
class CropBox:
    """A crop region. width/height are constant across a focus segment; x/y move."""
    x: int
    y: int
    width: int
    height: int


@dataclass
class FramePlan:
    """The framing decision for one output frame."""
    frame_num: int
    kind: FramingKind
    # FOCUS: `crop` is the single region.
    crop: Optional[CropBox] = None
    # SPLIT: `top` and `bottom` are the two regions (each rendered to half height).
    top: Optional[CropBox] = None
    bottom: Optional[CropBox] = None


@dataclass
class Analysis:
    """Full per-frame analysis before planning the crop path."""
    meta: VideoMeta
    detections: List[FrameDetections]
    scene_cuts: List[int]                       # frame indices where a cut begins
    motion_centroids: Optional[List[Optional[tuple]]] = None  # per-frame (x,y) of motion, or None
