import numpy as np

from clipperx.config import Config
from clipperx.planner import add_lookahead, plan
from clipperx.types import Sample


def sample(scores, shot=0):
    return Sample(0.0, shot, scores, 0.0, 1.0, 0)


def test_static_evidence_produces_static_camera():
    samples = [sample([0.1, 1.0, 0.1]) for _ in range(8)]
    centers = np.array([20.0, 50.0, 80.0])
    path = plan(samples, centers, 100, Config(candidate_count=3, sample_fps=4))
    assert np.allclose(path, 50.0)


def test_cut_allows_instant_target_change():
    samples = [
        sample([1.0, 0.0, 0.0], 0),
        sample([1.0, 0.0, 0.0], 0),
        sample([0.0, 0.0, 1.0], 1),
        sample([0.0, 0.0, 1.0], 1),
    ]
    centers = np.array([10.0, 50.0, 90.0])
    path = plan(samples, centers, 100, Config(candidate_count=3, sample_fps=4))
    assert path[0] == 10.0
    assert path[-1] == 90.0


def test_lookahead_adds_future_evidence():
    samples = [sample([1.0, 0.0]), sample([0.0, 1.0]), sample([0.0, 1.0])]
    evidence = add_lookahead(
        samples, Config(candidate_count=3, sample_fps=1, lookahead_seconds=2)
    )
    assert evidence[0, 1] > 0
    assert evidence[2, 1] == 1.0
