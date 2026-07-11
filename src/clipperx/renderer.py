from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .config import Config
from .types import Sample, VideoInfo


def render(
    source: Path,
    target: Path,
    info: VideoInfo,
    samples: list[Sample],
    camera: np.ndarray,
    config: Config,
) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg is required and was not found on PATH")
    scale = info.width / info.analysis_width
    crop_width = int(round(info.height * 9 / 16))
    crop_width -= crop_width % 2
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="clipperx-") as temporary:
        commands = Path(temporary) / "camera.txt"
        lines: list[str] = []
        for sample, center in zip(samples, camera * scale, strict=True):
            left = int(np.clip(round(center - crop_width / 2), 0, info.width - crop_width))
            lines.append(f"{sample.time:.6f} crop x {left};")
        commands.write_text("\n".join(lines), encoding="utf-8")
        video_filter = (
            f"sendcmd=f='{commands.as_posix()}',"
            f"crop@crop=w={crop_width}:h=ih:x='(iw-{crop_width})/2':y=0,"
            f"scale={config.output_width}:{config.output_height}:flags=lanczos"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(source), "-vf", video_filter,
                "-c:v", "libx264", "-preset", "medium", "-crf", str(config.crf),
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart", str(target),
            ],
            check=True,
        )
