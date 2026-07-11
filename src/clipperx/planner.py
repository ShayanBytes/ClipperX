from __future__ import annotations

import math

import numpy as np

from .config import Config
from .types import Sample


def add_lookahead(samples: list[Sample], config: Config) -> np.ndarray:
    evidence = np.asarray([sample.scores for sample in samples], dtype=np.float64)
    result = evidence.copy()
    horizon = max(0, int(round(config.lookahead_seconds * config.sample_fps)))
    for distance in range(1, horizon + 1):
        weight = 0.24 * math.exp(-distance / max(1, horizon))
        result[:-distance] += weight * evidence[distance:]
    return result


def plan(
    samples: list[Sample], centers: np.ndarray, frame_width: int, config: Config
) -> np.ndarray:
    evidence = add_lookahead(samples, config)
    count, candidates = evidence.shape
    if count == 1:
        return np.asarray([centers[int(np.argmax(evidence[0]))]], dtype=float)
    invalid = -1e18
    dp = np.full((candidates, candidates), invalid)
    back = np.full((count, candidates, candidates), -1, np.int16)
    max_step = frame_width * config.max_pan_per_second / config.sample_fps

    cut = samples[0].shot != samples[1].shot
    for previous in range(candidates):
        for current in range(candidates):
            delta = abs(centers[current] - centers[previous])
            if not cut and delta > max_step:
                continue
            cost = 0.0 if cut else (
                config.velocity_cost * delta / frame_width
                + config.switch_cost * (previous != current)
            )
            dp[previous, current] = evidence[0, previous] + evidence[1, current] - cost

    for time in range(2, count):
        next_dp = np.full((candidates, candidates), invalid)
        cut = samples[time].shot != samples[time - 1].shot
        for previous in range(candidates):
            for current in range(candidates):
                delta = abs(centers[current] - centers[previous])
                if not cut and delta > max_step:
                    continue
                best_value, best_ancestor = invalid, -1
                for ancestor in range(candidates):
                    velocity = 0.0 if cut else delta / frame_width
                    acceleration = 0.0 if cut else abs(
                        (centers[current] - centers[previous])
                        - (centers[previous] - centers[ancestor])
                    ) / frame_width
                    cost = (
                        config.velocity_cost * velocity
                        + config.acceleration_cost * acceleration
                        + (0.0 if cut else config.switch_cost * (previous != current))
                    )
                    value = dp[ancestor, previous] + evidence[time, current] - cost
                    if value > best_value:
                        best_value, best_ancestor = value, ancestor
                next_dp[previous, current] = best_value
                back[time, previous, current] = best_ancestor
        dp = next_dp

    previous, current = np.unravel_index(np.argmax(dp), dp.shape)
    states = np.empty(count, np.int16)
    states[-2:] = (previous, current)
    for time in range(count - 1, 1, -1):
        states[time - 2] = back[time, states[time - 1], states[time]]
    path = centers[states].astype(float)
    smoothed = path.copy()
    for _ in range(config.smoothing_passes):
        for index in range(1, count - 1):
            same_shot = samples[index - 1].shot == samples[index].shot == samples[index + 1].shot
            if same_shot:
                smoothed[index] = (
                    0.25 * smoothed[index - 1]
                    + 0.50 * smoothed[index]
                    + 0.25 * smoothed[index + 1]
                )
    return smoothed
