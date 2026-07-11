from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from .config import Config
from .types import Sample, VideoInfo


def _normalize(values: np.ndarray) -> np.ndarray:
    values = values.astype(np.float32)
    lo, hi = np.percentile(values, (5, 95))
    if hi <= lo + 1e-6:
        return np.zeros_like(values)
    return np.clip((values - lo) / (hi - lo), 0, 1)


def _histogram(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 16], [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten()


def probe(path: Path, analysis_width: int) -> VideoInfo:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if width <= 0 or height <= 0 or frames <= 0:
        raise RuntimeError("Video metadata is invalid")
    scale = min(1.0, analysis_width / width)
    aw, ah = max(2, int(width * scale)), max(2, int(height * scale))
    crop_width = max(2, int(ah * 9 / 16))
    if crop_width >= aw:
        raise ValueError("Input is already portrait or too narrow for a 9:16 crop")
    return VideoInfo(
        path=path,
        fps=fps,
        width=width,
        height=height,
        frames=frames,
        duration=frames / fps,
        analysis_width=aw,
        analysis_height=ah,
        crop_width=crop_width,
    )


def _importance(
    frame: np.ndarray,
    previous_gray: np.ndarray | None,
    detector: cv2.CascadeClassifier,
    memory: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    detail = _normalize(cv2.GaussianBlur(cv2.Laplacian(gray, cv2.CV_32F) ** 2, (0, 0), 7))
    motion = (
        np.zeros_like(detail)
        if previous_gray is None
        else _normalize(cv2.GaussianBlur(cv2.absdiff(gray, previous_gray), (0, 0), 9))
    )
    face_map = np.zeros((height, width), np.float32)
    faces = detector.detectMultiScale(
        gray, 1.12, 4, minSize=(max(20, width // 30), max(20, width // 30))
    )
    yy, xx = np.mgrid[0:height, 0:width]
    for x, y, fw, fh in faces:
        cx, cy = x + fw / 2, y + fh * 0.65
        sx, sy = max(1, fw * 1.15), max(1, fh * 1.55)
        face_map += np.exp(-0.5 * (((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))
    face_map = np.clip(face_map, 0, 1)
    axis = np.linspace(-1, 1, width, dtype=np.float32)
    center_prior = np.exp(-1.8 * axis * axis)[None, :].repeat(height, axis=0)
    base = 0.34 * motion + 0.31 * face_map + 0.13 * detail + 0.08 * center_prior
    memory = base if memory is None else 0.82 * memory + 0.18 * base
    return base + 0.14 * memory, gray, memory, len(faces)


def score_windows(heat: np.ndarray, crop_width: int, centers: np.ndarray) -> np.ndarray:
    column_score = heat.mean(axis=0)
    integral = np.r_[0.0, np.cumsum(column_score, dtype=np.float64)]
    scores: list[float] = []
    for center in centers:
        left = int(round(center - crop_width / 2))
        left = max(0, min(heat.shape[1] - crop_width, left))
        right = left + crop_width
        score = (integral[right] - integral[left]) / crop_width
        edge_room = min(left, heat.shape[1] - right) / max(1, crop_width)
        scores.append(float(score - 0.012 * math.exp(-5 * edge_room)))
    return np.asarray(scores, dtype=np.float64)


def analyze(path: Path, config: Config) -> tuple[VideoInfo, list[Sample], np.ndarray]:
    config.validate()
    info = probe(path, config.analysis_width)
    centers = np.linspace(
        info.crop_width / 2,
        info.analysis_width - info.crop_width / 2,
        config.candidate_count,
    )
    detector = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    cap = cv2.VideoCapture(str(path))
    stride = max(1, int(round(info.fps / config.sample_fps)))
    previous_gray = previous_histogram = memory = None
    samples: list[Sample] = []
    shot = frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_index % stride:
            frame_index += 1
            continue
        proxy = cv2.resize(
            frame,
            (info.analysis_width, info.analysis_height),
            interpolation=cv2.INTER_AREA,
        )
        histogram = _histogram(proxy)
        if previous_histogram is not None:
            distance = cv2.compareHist(
                previous_histogram, histogram, cv2.HISTCMP_BHATTACHARYYA
            )
            if distance > config.cut_threshold:
                shot += 1
                previous_gray = memory = None
        heat, previous_gray, memory, face_count = _importance(
            proxy, previous_gray, detector, memory
        )
        scores = score_windows(heat, info.crop_width, centers)
        order = np.argsort(scores)
        best, second = scores[order[-1]], scores[order[-2]]
        confidence = float(np.clip((best - second) / (abs(best) + 1e-6) * 8, 0, 1))
        samples.append(
            Sample(
                time=frame_index / info.fps,
                shot=shot,
                scores=scores.tolist(),
                raw_best_x=float(centers[order[-1]]),
                confidence=confidence,
                face_count=face_count,
            )
        )
        previous_histogram = histogram
        frame_index += 1
    cap.release()
    if not samples:
        raise RuntimeError("No frames were analyzed")
    return info, samples, centers
