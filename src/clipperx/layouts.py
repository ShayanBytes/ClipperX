from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from .types import EntityObservation, InteractionEdge


class LayoutType(StrEnum):
    CROP = "crop"
    GROUP = "group"
    SPLIT = "split_screen"
    SAFE_WIDE = "safe_wide"


@dataclass(frozen=True, slots=True)
class Panel:
    center_x: float
    subject_ids: tuple[int, ...]
    weight: float


@dataclass(frozen=True, slots=True)
class LayoutCandidate:
    layout: LayoutType
    panels: tuple[Panel, ...]
    utility: float
    confidence: float
    reason: str


def _relation_strength(
    left_id: int,
    right_id: int,
    interactions: list[InteractionEdge],
) -> float:
    for edge in interactions:
        pair = {edge.source_id, edge.target_id}
        if pair == {left_id, right_id}:
            return edge.strength * edge.confidence
    return 0.0


def generate_layouts(
    entities: list[EntityObservation],
    interactions: list[InteractionEdge],
    frame_width: int,
    crop_width: int,
) -> list[LayoutCandidate]:
    candidates: list[LayoutCandidate] = []
    visible = [entity for entity in entities if entity.missed == 0 and entity.confidence >= 0.35]
    for entity in visible:
        candidates.append(
            LayoutCandidate(
                layout=LayoutType.CROP,
                panels=(Panel(entity.center[0], (entity.track_id,), 1.0),),
                utility=entity.importance + 0.2 * entity.confidence,
                confidence=entity.confidence,
                reason="highest local entity retention",
            )
        )

    if len(visible) >= 2:
        ranked = sorted(visible, key=lambda item: item.importance, reverse=True)
        first, second = ranked[:2]
        left = min(first.bbox[0], second.bbox[0])
        right = max(first.bbox[0] + first.bbox[2], second.bbox[0] + second.bbox[2])
        span = right - left
        relation = _relation_strength(first.track_id, second.track_id, interactions)
        joint_importance = first.importance + second.importance
        joint_confidence = min(first.confidence, second.confidence)
        if span <= crop_width * 0.92:
            candidates.append(
                LayoutCandidate(
                    layout=LayoutType.GROUP,
                    panels=(
                        Panel(
                            center_x=float(np.clip((left + right) / 2, crop_width / 2, frame_width - crop_width / 2)),
                            subject_ids=(first.track_id, second.track_id),
                            weight=1.0,
                        ),
                    ),
                    utility=joint_importance + 0.35 * relation + 0.15,
                    confidence=joint_confidence,
                    reason="important pair fits one vertical viewport",
                )
            )
        elif joint_importance >= 0.72 and relation >= 0.18 and joint_confidence >= 0.65:
            total = max(1e-6, first.importance + second.importance)
            candidates.append(
                LayoutCandidate(
                    layout=LayoutType.SPLIT,
                    panels=(
                        Panel(first.center[0], (first.track_id,), first.importance / total),
                        Panel(second.center[0], (second.track_id,), second.importance / total),
                    ),
                    utility=joint_importance + 0.45 * relation - 0.18,
                    confidence=joint_confidence,
                    reason="related high-importance subjects cannot coexist in one crop",
                )
            )

    evidence_confidence = max((item.confidence for item in candidates), default=0.0)
    candidates.append(
        LayoutCandidate(
            layout=LayoutType.SAFE_WIDE,
            panels=(Panel(frame_width / 2, tuple(item.track_id for item in visible), 1.0),),
            utility=0.42 + 0.2 * (1.0 - evidence_confidence),
            confidence=1.0,
            reason="conservative fallback preserves source context",
        )
    )
    return sorted(candidates, key=lambda item: item.utility, reverse=True)


def select_layout(
    candidates: list[LayoutCandidate],
    previous: LayoutCandidate | None = None,
    switch_penalty: float = 0.14,
) -> LayoutCandidate:
    if not candidates:
        raise ValueError("At least one layout candidate is required")
    scored: list[tuple[float, LayoutCandidate]] = []
    for candidate in candidates:
        penalty = 0.0
        if previous is not None and candidate.layout != previous.layout:
            penalty = switch_penalty
        if candidate.layout == LayoutType.SPLIT and candidate.confidence < 0.7:
            penalty += 0.25
        scored.append((candidate.utility - penalty, candidate))
    return max(scored, key=lambda item: item[0])[1]
