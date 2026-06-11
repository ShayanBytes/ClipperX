"""
scene_detector.py - shot-cut detection via PySceneDetect.

Returns the frame indices where a new shot begins. The crop planner uses these
to SNAP the crop instantly (no cinematic slide) across hard camera cuts, and the
speaker tracker uses them to reset identity tracks.

This replaces 0.2's broken homemade detector, which fed a PySceneDetect-scale
threshold (27.0) into a 0..1 histogram comparison and therefore never fired.
"""
from __future__ import annotations

from typing import Callable, List, Optional

from scenedetect import open_video, SceneManager
from scenedetect.detectors import ContentDetector


def detect_scene_cuts(
    video_path: str,
    threshold: float = 27.0,
    min_scene_len: int = 12,
    progress_cb: Optional[Callable[[float, str], None]] = None,
) -> List[int]:
    video = open_video(video_path)
    manager = SceneManager()
    manager.add_detector(
        ContentDetector(threshold=float(threshold), min_scene_len=int(min_scene_len))
    )
    manager.detect_scenes(video=video, show_progress=False)
    scenes = manager.get_scene_list()

    # get_scene_list returns (start, end) timecode pairs; a cut begins at each
    # scene's start frame (skip the first, which is frame 0).
    cuts: List[int] = []
    for start, _end in scenes:
        f = start.get_frames()
        if f > 0:
            cuts.append(f)

    if progress_cb:
        progress_cb(1.0, "Scene detection")
    return cuts
