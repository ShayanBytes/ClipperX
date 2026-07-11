from clipperx.tracking import CentroidTracker


def test_identity_persists_for_nearby_detection():
    tracker = CentroidTracker()
    first = tracker.update([(10, 10, 20, 20)], 100, 100)
    second = tracker.update([(13, 10, 20, 20)], 100, 100)
    assert first[0].track_id == second[0].track_id
    assert second[0].age == 2


def test_new_distant_detection_gets_new_identity():
    tracker = CentroidTracker(match_radius=0.1)
    first = tracker.update([(0, 0, 10, 10)], 100, 100)
    second = tracker.update([(90, 90, 10, 10)], 100, 100)
    assert first[0].track_id != second[-1].track_id


def test_track_survives_short_occlusion():
    tracker = CentroidTracker(max_missed=2)
    track_id = tracker.update([(10, 10, 20, 20)], 100, 100)[0].track_id
    hidden = tracker.update([], 100, 100)
    restored = tracker.update([(11, 10, 20, 20)], 100, 100)
    assert hidden[0].missed == 1
    assert restored[0].track_id == track_id
