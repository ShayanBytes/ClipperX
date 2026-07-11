from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .config import Config
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
    render(source, target, info, samples, camera, config)
    trace = {
        "schema_version": 2,
        "engine_version": "0.2.0",
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
            }
            for sample, center in zip(samples, camera, strict=True)
        ],
    }
    trace_path = target.with_suffix(".json")
    trace_path.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    return target
