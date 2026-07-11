from clipperx.narrative import infer_interactions, score_entities
from clipperx.types import EntityObservation


def entity(track_id, x, age=4):
    return EntityObservation(
        track_id=track_id,
        kind="person",
        bbox=(x, 10, 20, 30),
        center=(x + 10, 25),
        velocity=(0, 0),
        confidence=1.0,
        age=age,
        missed=0,
    )


def test_near_people_create_proximity_edge():
    entities = [entity(1, 10), entity(2, 30)]
    edges = infer_interactions(entities, 100, 100)
    assert len(edges) == 1
    assert edges[0].relation == "proximity"


def test_importance_is_normalized():
    entities = [entity(1, 10), entity(2, 60)]
    scored = score_entities(entities, [], 100, 100)
    assert abs(sum(item.importance for item in scored) - 1.0) < 1e-9
