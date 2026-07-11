from clipperx.layouts import LayoutType, generate_layouts, select_layout
from clipperx.types import EntityObservation, InteractionEdge


def entity(track_id, x, importance=0.5):
    return EntityObservation(
        track_id=track_id,
        kind="person",
        bbox=(x, 10, 20, 30),
        center=(x + 10, 25),
        velocity=(0, 0),
        confidence=0.95,
        age=10,
        missed=0,
        importance=importance,
    )


def test_group_layout_when_pair_fits():
    candidates = generate_layouts(
        [entity(1, 20), entity(2, 45)],
        [InteractionEdge(1, 2, "proximity", 0.8, 1.0)],
        frame_width=160,
        crop_width=80,
    )
    assert any(item.layout == LayoutType.GROUP for item in candidates)


def test_split_layout_when_important_pair_is_separated():
    candidates = generate_layouts(
        [entity(1, 5), entity(2, 135)],
        [InteractionEdge(1, 2, "gaze", 0.9, 1.0)],
        frame_width=160,
        crop_width=50,
    )
    assert any(item.layout == LayoutType.SPLIT for item in candidates)


def test_low_confidence_avoids_split():
    first = entity(1, 5)
    second = EntityObservation(
        track_id=2,
        kind="person",
        bbox=(135, 10, 20, 30),
        center=(145, 25),
        velocity=(0, 0),
        confidence=0.4,
        age=2,
        missed=0,
        importance=0.5,
    )
    candidates = generate_layouts(
        [first, second],
        [InteractionEdge(1, 2, "gaze", 0.9, 1.0)],
        frame_width=160,
        crop_width=50,
    )
    assert all(item.layout != LayoutType.SPLIT for item in candidates)
    assert select_layout(candidates).layout != LayoutType.SPLIT
