"""
pipeline.py - orchestrate the full reframe: analyze -> plan -> render.

Pure backend (no Qt), so it runs headless from the CLI and inside the GUI's
worker thread alike. Reports coarse progress through `progress_cb(percent, label)`
where percent is 0..1 over the whole job.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Callable, Optional

import cv2

from backend.models import Analysis, VideoMeta
from backend.reframer.detector import FaceAnalyzer
from backend.reframer.scene_detector import detect_scene_cuts
from backend.reframer.speaker import SpeakerTracker
from backend.reframer.crop_planner import CropPlanner
from backend.reframer.renderer import VideoRenderer

# import config + presets from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CONFIG  # noqa: E402
from presets import apply_preset  # noqa: E402

ProgressCB = Optional[Callable[[float, str], None]]


def probe_meta(video_path: str) -> VideoMeta:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open video: {video_path}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    duration = total / fps if fps > 0 else 0.0
    return VideoMeta(width=w, height=h, fps=fps, total_frames=total,
                     duration=duration, path=video_path)


def _stage(progress_cb: ProgressCB, base: float, span: float, label: str):
    if progress_cb is None:
        return None

    def cb(frac: float, _label: str):
        progress_cb(base + span * max(0.0, min(1.0, frac)), label)
    return cb


def reframe(
    video_path: str,
    output_path: Optional[str] = None,
    config: Optional[dict] = None,
    progress_cb: ProgressCB = None,
    preset: str = "auto",
) -> str:
    # An explicit config wins; otherwise start from CONFIG and apply the chosen preset
    # (a content-type policy profile that tunes the engine - "auto" is a no-op).
    cfg = config if config is not None else apply_preset(CONFIG, preset)
    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    if output_path is None:
        export_dir = cfg.get("export_dir", "exports")
        os.makedirs(export_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(video_path))[0]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(export_dir, f"{base}_vertical_{stamp}.mp4")

    meta = probe_meta(video_path)

    # 1. faces + motion  (0 .. 0.50)
    analyzer = FaceAnalyzer(cfg)
    detections, motion = analyzer.analyze(meta, _stage(progress_cb, 0.0, 0.50, "Analyzing faces"))
    analyzer.close()

    # 2. scene cuts  (0.50 .. 0.60)
    cuts = detect_scene_cuts(
        video_path,
        threshold=cfg["scene_threshold"],
        min_scene_len=cfg["min_scene_len_frames"],
        progress_cb=_stage(progress_cb, 0.50, 0.10, "Detecting scene cuts"),
    )

    # 3. speaker intents + crop plan  (0.60 .. 0.65)
    if progress_cb:
        progress_cb(0.60, "Planning shots")
    tracker = SpeakerTracker(cfg, meta.width, meta.height)
    intents = tracker.run(detections, cuts)
    planner = CropPlanner(cfg, meta)
    plans = planner.plan(intents, motion)

    # 4. render  (0.65 .. 1.0)
    renderer = VideoRenderer(cfg)
    renderer.render(meta, plans, output_path, _stage(progress_cb, 0.65, 0.35, "Rendering"))

    if progress_cb:
        progress_cb(1.0, "Done")
    return output_path


def _print_progress(pct: float, label: str):
    bar = int(pct * 30)
    sys.stdout.write(f"\r  [{'#' * bar}{'.' * (30 - bar)}] {pct*100:5.1f}%  {label}      ")
    sys.stdout.flush()


if __name__ == "__main__":
    from presets import preset_names

    args = sys.argv[1:]
    preset = "auto"
    if "--preset" in args:
        i = args.index("--preset")
        preset = args[i + 1]
        del args[i:i + 2]
    if not args:
        print("Usage: python -m backend.pipeline <input_video> [output_video] "
              f"[--preset NAME]\n  presets: {', '.join(preset_names())}")
        sys.exit(1)
    inp = args[0]
    outp = args[1] if len(args) > 1 else None
    print(f"ClipperX - reframing 16:9 -> 9:16  (preset: {preset})")
    out = reframe(inp, outp, progress_cb=_print_progress, preset=preset)
    print(f"\n\nSaved: {out}")
