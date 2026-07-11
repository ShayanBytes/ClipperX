from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np

from .config import Config
from .narrative import apply_entity_evidence, infer_interactions, score_entities
from .tracking import CentroidTracker
from .types import Sample, VideoInfo


def _normalize(values: np.ndarray) -> np.ndarray:
    values = values.astype(np.float32)
    lo, hi = np.percentile(values, (5, 95))
    if hi <= lo + 1e-6:
        return np.zeros_like(values)
    return np.clip((values - lo) / (hi - lo), 0, 1)


def _histogram(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [32, 16], [0, 180, 0, 256])
    return cv2.normalize(histogram, histogram).flatten()


def probe(path: Path, analysis_width: int) -> VideoInfo:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    capture.release()
    if width <= 0 or height <= 0 or frames <= 0:
        raise RuntimeError("Video metadata is invalid")
    scale = min(1.0, analysis_width / width)
    proxy_width = max(2, int(width * scale))
    proxy_height = max(2, int(height * scale))
    crop_width = max(2, int(proxy_height * 9 / 16))
    if crop_width >= proxy_width:
        raise ValueError("Input is already portrait or too narrow for a 9:16 crop")
    return VideoInfo(
        path=path,
        fps=fps,
        width=width,
        height=height,
        frames=frames,
        duration=frames / fps,
        analysis_width=proxy_width,
        analysis_height=proxy_height,
        crop_width=crop_width,
    )


def _visual_evidence(
    frame: np.ndarray,
    previous_gray: np.ndarray | None,
    detector: cv2.CascadeClassifier,
    memory: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[tuple[float, float, float, float]]]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    detail = _normalize(cv2.GaussianBlur(cv2.Laplacian(gray, cv2.CV_32F) ** 2, (0, 0), 7))
    if previous_gray is None:
        motion = np.zeros_like(detail)
    else:
        difference = cv2.absdiff(gray, previous_gray)
        motion = _normalize(cv2.GaussianBlur(difference, (0, 0), 9))
    face_map = np.zeros((height, width), np.float32)
    detections = detector.detectMultiScale(
        gray,
        1.12,
        4,
        minSize=(max(20, width // 30), max(20, width // 30)),
    )
    boxes = [tuple(float(value) for value in detection) for detection in detections]
    yy, xx = np.mgrid[0:height, 0:width]
    for x, y, face_width, face_height in boxes:
        cx, cy = x + face_width / 2, y + face_height * 0.65
        sx, sy = max(1, face_width * 1.15), max(1, face_height * 1.55)
        face_map += np.exp(-0.5 * (((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))
    face_map = np.clip(face_map, 0, 1)
    axis = np.linspace(-1, 1, width, dtype=np.float32)
    center_prior = np.exp(-1.8 * axis * axis)[None, :].repeat(height, axis=0)
    base = 0.34 * motion + 0.31 * face_map + 0.13 * detail + 0.08 * center_prior
    memory = base if memory is None else 0.82 * memory + 0.18 * base
    return base + 0.14 * memory, gray, memory, boxes


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
    tracker = CentroidTracker()
    capture = cv2.VideoCapture(str(path))
    stride = max(1, int(round(info.fps / config.sample_fps)))
    previous_gray = previous_histogram = memory = None
    samples: list[Sample] = []
    shot = frame_index = 0
    while True:
        ok, frame = capture.read()
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
                previous_histogram,
                histogram,
                cv2.HISTCMP_BHATTACHARYYA,
            )
            if distance > config.cut_threshold:
                shot += 1
                previous_gray = memory = None
                tracker.reset()
        heat, previous_gray, memory, boxes = _visual_evidence(
            proxy, previous_gray, detector, memory
        )
        entities = tracker.update(boxes, info.analysis_width, info.analysis_height)
        interactions = infer_interactions(
            entities, info.analysis_width, info.analysis_height
        )
        entities = score_entities(
            entities, interactions, info.analysis_width, info.analysis_height
        )
        heat = apply_entity_evidence(heat, entities)
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
                face_count=len(boxes),
                entities=entities,
                interactions=interactions,
            )
        )
        previous_histogram = histogram
        frame_index += 1
    capture.release()
    if not samples:
        raise RuntimeError("No frames were analyzed")
    return info, samples, centers
