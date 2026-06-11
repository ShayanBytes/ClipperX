# ClipperX 0.3

Turn long 16:9 talking videos into cinematic **9:16** vertical shorts.

This version is **Phase 1: the auto-reframe engine** + a desktop app.
Drop a video → Generate → preview → Export. No AI moment finder yet — you pick the
clip, ClipperX reframes it beautifully.

## What it does

- **Single person** — tracks the subject (MediaPipe **PoseLandmarker**, so it works
  even on wide stage / full-body shots where face detection fails) and follows them
  like a calm camera operator: dead-zone, inertia (EMA), speed limit, and a hard
  **snap on every scene cut** (no awkward post-cut sliding).
- **Subject steps out of frame** (to show something) — the crop *holds* and gently
  drifts toward on-screen motion instead of cutting to an empty center.
- **Two people** — hard-cuts to whoever is talking (active speaker from face
  `jawOpen` motion, with hysteresis so it doesn't flicker on quick exchanges), and
  automatically switches to a **top/bottom split-screen** during joint moments
  (both laughing / talking together).

## Architecture

```
main.py                       launches the desktop app
config.py                     every tunable parameter (all actually used)
backend/
  models.py                   dataclasses shared across stages
  pipeline.py                 orchestrates analyze -> plan -> render (also a CLI)
  reframer/
    detector.py               PoseLandmarker position + FaceLandmarker jawOpen + motion
    scene_detector.py         PySceneDetect shot cuts
    speaker.py                identity tracking, active speaker, joint-moment split
    crop_planner.py           dead-zone + inertia + speed-limit + snap (the cinematic core)
    renderer.py               applies the per-frame crop, pipes to ffmpeg, muxes audio
frontend/
  main_window.py              drop -> Generate (background thread) -> preview -> Export
  widgets.py                  drag-and-drop zone
scripts/debug_overlay.py      draws the crop + speaker/split decisions on the source (tuning)
models/                       MediaPipe .task model files (required, see below)
```

## Setup

Requires **ffmpeg** on PATH and Python 3.11–3.13.

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
```

The MediaPipe model files in `models/` are required:

- `models/pose_landmarker_full.task`
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task
- `models/face_landmarker.task`
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task

## Run

Desktop app:

```bash
python main.py
```

Command line (headless):

```bash
python -m backend.pipeline input.mp4                 # -> exports/input_vertical_<time>.mp4
python -m backend.pipeline input.mp4 out.mp4
```

Tuning overlay (see what the engine decided, on the original footage):

```bash
python scripts/debug_overlay.py input.mp4            # -> exports/input_debug.mp4
```

## Tuning

All knobs live in `config.py`. The ones you'll reach for first:

- `dead_zone_ratio` — bigger = crop moves less (more breathing room).
- `ema_alpha` — lower = smoother / laggier camera; higher = more responsive.
- `max_velocity_px_per_frame` — caps how fast the crop can pan.
- `scene_threshold` — lower = more scene cuts detected.
- `speaker_switch_hold_frames` — how long a new speaker must lead before we cut to them.
- `joint_hold_frames` / `both_active_threshold` — how eagerly it splits to show both.
```
