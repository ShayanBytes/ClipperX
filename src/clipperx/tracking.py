from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import EntityObservation


@dataclass(slots=True)
class _Track:
    track_id: int
    bbox: np.ndarray
    center: np.ndarray
    velocity: np.ndarray
    age: int = 1
    missed: int = 0
    confidence: float = 1.0


class CentroidTracker:
    """Deterministic lightweight tracker for the CPU baseline.

    This is intentionally replaceable by ByteTrack or BoT-SORT. It provides a
    stable runtime contract now, without adding a heavyweight dependency.
    """

    def __init__(self, max_missed: int = 5, match_radius: float = 0.18) -> None:
        self.max_missed = max_missed
        self.match_radius = match_radius
        self._next_id = 1
        self._tracks: dict[int, _Track] = {}

    def reset(self) -> None:
        self._tracks.clear()

    @staticmethod
    def _center(box: np.ndarray) -> np.ndarray:
        x, y, width, height = box
        return np.asarray((x + width / 2, y + height / 2), dtype=np.float64)

    def update(
        self,
        boxes: list[tuple[float, float, float, float]],
        frame_width: int,
        frame_height: int,
    ) -> list[EntityObservation]:
        detections = [np.asarray(box, dtype=np.float64) for box in boxes]
        diagonal = max(1.0, float(np.hypot(frame_width, frame_height)))
        unmatched_tracks = set(self._tracks)
        unmatched_detections = set(range(len(detections)))
        pairs: list[tuple[float, int, int]] = []

        for track_id, track in self._tracks.items():
            predicted = track.center + track.velocity
            for index, detection in enumerate(detections):
                distance = float(np.linalg.norm(self._center(detection) - predicted) / diagonal)
                pairs.append((distance, track_id, index))

        for distance, track_id, index in sorted(pairs):
            if distance > self.match_radius:
                break
            if track_id not in unmatched_tracks or index not in unmatched_detections:
                continue
            track = self._tracks[track_id]
            new_center = self._center(detections[index])
            measured_velocity = new_center - track.center
            track.velocity = 0.65 * track.velocity + 0.35 * measured_velocity
            track.center = new_center
            track.bbox = detections[index]
            track.age += 1
            track.missed = 0
            track.confidence = min(1.0, track.confidence + 0.08)
            unmatched_tracks.remove(track_id)
            unmatched_detections.remove(index)

        for track_id in unmatched_tracks:
            track = self._tracks[track_id]
            track.center += track.velocity
            track.missed += 1
            track.age += 1
            track.confidence *= 0.72

        for index in unmatched_detections:
            detection = detections[index]
            center = self._center(detection)
            self._tracks[self._next_id] = _Track(
                track_id=self._next_id,
                bbox=detection,
                center=center,
                velocity=np.zeros(2, dtype=np.float64),
            )
            self._next_id += 1

        self._tracks = {
            track_id: track
            for track_id, track in self._tracks.items()
            if track.missed <= self.max_missed
        }
        return [
            EntityObservation(
                track_id=track.track_id,
                kind="person",
                bbox=tuple(float(value) for value in track.bbox),
                center=(float(track.center[0]), float(track.center[1])),
                velocity=(float(track.velocity[0]), float(track.velocity[1])),
                confidence=float(track.confidence),
                age=track.age,
                missed=track.missed,
            )
            for track in sorted(self._tracks.values(), key=lambda item: item.track_id)
        ]
