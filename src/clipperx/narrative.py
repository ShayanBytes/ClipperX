from __future__ import annotations

from dataclasses import replace

import numpy as np

from .types import EntityObservation, InteractionEdge


def infer_interactions(
    entities: list[EntityObservation], frame_width: int, frame_height: int
) -> list[InteractionEdge]:
    edges: list[InteractionEdge] = []
    diagonal = max(1.0, float(np.hypot(frame_width, frame_height)))
    for source_index, source in enumerate(entities):
        for target in entities[source_index + 1 :]:
            distance = float(np.linalg.norm(np.subtract(source.center, target.center)) / diagonal)
            proximity = float(np.clip(1.0 - distance / 0.45, 0.0, 1.0))
            if proximity > 0.05:
                confidence = min(source.confidence, target.confidence)
                edges.append(
                    InteractionEdge(
                        source_id=source.track_id,
                        target_id=target.track_id,
                        relation="proximity",
                        strength=proximity,
                        confidence=confidence,
                    )
                )
    return edges


def score_entities(
    entities: list[EntityObservation],
    edges: list[InteractionEdge],
    frame_width: int,
    frame_height: int,
) -> list[EntityObservation]:
    if not entities:
        return []
    centrality = {entity.track_id: 0.0 for entity in entities}
    for edge in edges:
        value = edge.strength * edge.confidence
        centrality[edge.source_id] += value
        centrality[edge.target_id] += value
    logits: list[float] = []
    for entity in entities:
        _, _, width, height = entity.bbox
        area = float(np.clip(width * height / max(1, frame_width * frame_height), 0.0, 1.0))
        speed = float(np.hypot(*entity.velocity) / max(1, frame_width))
        continuity = float(np.tanh(entity.age / 8))
        visibility = entity.confidence * (0.55 if entity.missed else 1.0)
        logit = (
            1.4 * np.sqrt(area)
            + 0.8 * np.clip(speed * 8, 0, 1)
            + 0.7 * continuity
            + 0.9 * centrality[entity.track_id]
            + 0.8 * visibility
        )
        logits.append(float(logit))
    values = np.asarray(logits, dtype=np.float64)
    probabilities = np.exp(values - values.max())
    probabilities /= probabilities.sum()
    return [
        replace(entity, importance=float(probability))
        for entity, probability in zip(entities, probabilities, strict=True)
    ]


def apply_entity_evidence(
    heat: np.ndarray,
    entities: list[EntityObservation],
) -> np.ndarray:
    if not entities:
        return heat
    height, width = heat.shape
    yy, xx = np.mgrid[0:height, 0:width]
    narrative = np.zeros_like(heat, dtype=np.float32)
    for entity in entities:
        x, y, box_width, box_height = entity.bbox
        cx = x + box_width / 2
        cy = y + box_height * 0.55
        sx = max(4.0, box_width * 1.25)
        sy = max(4.0, box_height * 1.35)
        narrative += entity.importance * np.exp(
            -0.5 * (((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2)
        )
    return heat + 0.45 * np.clip(narrative, 0, 1)
