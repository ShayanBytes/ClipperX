from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .config import Config
from .layouts import generate_layouts, select_layout
from .perception import analyze
from .planner import plan
from .renderer import render


def reframe(source: Path, target: Path, config: Config | None = None) -> Path:
    config = config or Config()
    source, target = Path(source), Path(target)
    if not source.is_file():
        raise FileNotFoundError(source)
    info, samples, centers = analyze(source, config)
    camera = plan(samples, centers, info.analysis_width, config)
    selected_layouts = []
    previous_layout = None
    for sample in samples:
        candidates = generate_layouts(
            sample.entities,
            sample.interactions,
            info.analysis_width,
            info.crop_width,
        )
        selected = select_layout(candidates, previous_layout)
        selected_layouts.append((selected, candidates[:4]))
        previous_layout = selected
    render(source, target, info, samples, camera, config)
    trace = {
        "schema_version": 3,
        "engine_version": "0.3.0",
        "config": asdict(config),
        "video": {**asdict(info), "path": str(info.path)},
        "camera": [
            {
                "time": sample.time,
                "shot": sample.shot,
                "center_x_proxy": float(center),
                "raw_best_x_proxy": sample.raw_best_x,
                "confidence": sample.confidence,
                "face_count": sample.face_count,
                "entities": [asdict(entity) for entity in sample.entities],
                "interactions": [asdict(edge) for edge in sample.interactions],
                "selected_layout": asdict(layout),
                "layout_alternatives": [asdict(item) for item in alternatives],
            }
            for sample, center, (layout, alternatives) in zip(
                samples,
                camera,
                selected_layouts,
                strict=True,
            )
        ],
    }
    trace_path = target.with_suffix(".json")
    trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    return target
