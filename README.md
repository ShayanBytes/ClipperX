# ClipperX

Story-aware 16:9 to 9:16 video reframing, built as a deterministic and inspectable engine. Runtime makes no LLM or network calls.

## Current milestone

This first production baseline provides:

- timestamped low-resolution proxy analysis
- hard-cut detection
- face, motion, detail, and composition evidence
- candidate vertical viewports
- bounded-look-ahead evidence
- global dynamic-programming camera planning
- minimum-jitter trajectory smoothing
- full-resolution FFmpeg rendering
- JSON decision traces
- deterministic tests for planner behavior

The architecture deliberately separates perception, planning, and rendering. Learned narrative attention, interaction graphs, reaction inference, group layouts, and split-screen will plug into the evidence and candidate interfaces without replacing the safety planner.

## Requirements

- Python 3.11+
- FFmpeg available on `PATH`

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Run

```bash
clipperx input.mp4 output.mp4
```

Low-memory mode for older Intel Macs:

```bash
clipperx input.mp4 output.mp4 --analysis-width 384 --sample-fps 3
```

The output video is accompanied by `output.json`, containing every sampled timestamp, shot ID, confidence value, raw target, and planned virtual-camera position.

## Test

```bash
pytest
```

## Runtime contract

ClipperX never invents story-critical pixels. If evidence is ambiguous, future layout modules must prefer a wider conservative presentation over aggressive movement or generative alteration.
