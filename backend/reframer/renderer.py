"""
renderer.py - apply the per-frame crop path and encode the vertical output.

THE key fix vs 0.2: 0.2 computed a crop path then rendered the whole video with a
single frozen crop. Here every output frame uses *its own* crop box.

Pipeline: OpenCV decodes each source frame -> we crop/resize (or build a split
stack) -> raw BGR is piped to one ffmpeg process that encodes H.264 and muxes the
ORIGINAL audio back in. Per-frame motion, good quality, sound preserved, one pass.
"""
from __future__ import annotations

import subprocess
from typing import Callable, List, Optional

import cv2
import numpy as np

from backend.models import CropBox, FramePlan, FramingKind, VideoMeta


def _crop_resize(frame: np.ndarray, box: CropBox, out_w: int, out_h: int) -> np.ndarray:
    H, W = frame.shape[:2]
    x = max(0, min(box.x, W - 1))
    y = max(0, min(box.y, H - 1))
    x2 = min(W, x + box.width)
    y2 = min(H, y + box.height)
    region = frame[y:y2, x:x2]
    if region.shape[0] != box.height or region.shape[1] != box.width:
        # safety pad if clamped (rare); keeps output size exact
        region = cv2.copyMakeBorder(
            region, 0, max(0, box.height - region.shape[0]),
            0, max(0, box.width - region.shape[1]), cv2.BORDER_REPLICATE,
        )
    return cv2.resize(region, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)


class VideoRenderer:
    def __init__(self, config: dict):
        self.cfg = config
        self.out_w = int(config["output_width"])
        self.out_h = int(config["output_height"])
        self.half = self.out_h // 2
        self.divider = int(config.get("split_divider_px", 0))

    def render(
        self,
        meta: VideoMeta,
        plans: List[FramePlan],
        output_path: str,
        progress_cb: Optional[Callable[[float, str], None]] = None,
    ):
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", f"{self.out_w}x{self.out_h}",
            "-r", f"{meta.fps:.6f}",
            "-i", "pipe:0",
            "-i", meta.path,
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", str(self.cfg["crf"]), "-preset", str(self.cfg["preset"]),
            "-c:a", "aac", "-b:a", "160k",
            "-shortest",
            output_path,
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)

        cap = cv2.VideoCapture(meta.path)
        n = len(plans)
        i = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                plan = plans[i] if i < n else plans[-1]
                out = self._compose(frame, plan)
                proc.stdin.write(out.tobytes())
                i += 1
                if progress_cb and meta.total_frames > 0 and i % 15 == 0:
                    progress_cb(i / meta.total_frames, "Rendering")
        finally:
            cap.release()
            if proc.stdin:
                proc.stdin.close()
            proc.wait()
        if proc.returncode not in (0, None):
            raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")

    def _compose(self, frame: np.ndarray, plan: FramePlan) -> np.ndarray:
        if plan.kind == FramingKind.SPLIT and plan.top and plan.bottom:
            top = _crop_resize(frame, plan.top, self.out_w, self.half)
            bottom = _crop_resize(frame, plan.bottom, self.out_w, self.out_h - self.half)
            out = np.vstack([top, bottom])
            if self.divider > 0:
                a = max(0, self.half - self.divider // 2)
                b = min(self.out_h, a + self.divider)
                out[a:b, :] = 0
            return np.ascontiguousarray(out)
        # focus (or absent -> still a valid clamped crop)
        box = plan.crop if plan.crop else CropBox(0, 0, frame.shape[1], frame.shape[0])
        return np.ascontiguousarray(_crop_resize(frame, box, self.out_w, self.out_h))
