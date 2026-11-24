"""Automatic road zones: vehicle paths grouped by direction become zones."""
from app.video.autozones import zones_from_tracks


def _path(x0, y0, x1, y1, n=20):
    return [(x0 + (x1 - x0) * i / (n - 1), y0 + (y1 - y0) * i / (n - 1)) for i in range(n)]


def test_four_approaches_give_four_roads():
    tracks, tid = {}, 0
    for k in range(4):  # several vehicles on each approach, slightly offset
        off = k * 8
        for path in (_path(20, 260 + off, 300, 260 + off),   # from the left, heading right
                     _path(620, 200 + off, 340, 200 + off),  # from the right, heading left
                     _path(300 + off, 20, 300 + off, 220),   # from the top, heading down
                     _path(360 + off, 460, 360 + off, 280)):  # from the bottom, heading up
            tracks[tid] = path
            tid += 1
    roads = zones_from_tracks(tracks, 640, 480)
    assert len(roads) == 4
    assert {r["side"] for r in roads} == {"left", "right", "top", "bottom"}
    for r in roads:
        assert len(r["polygon"]) >= 3
        assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in r["polygon"])


def test_parked_vehicles_give_no_roads():
    tracks = {i: [(100 + i, 100)] * 20 for i in range(10)}
    assert zones_from_tracks(tracks, 640, 480) == []


def test_riders_are_not_pedestrians():
    import numpy as np
    from app.video.detector import mark_riders
    xyxy = np.array([
        [100, 100, 160, 260],   # person sitting on the motorbike below
        [90, 180, 170, 280],    # motorbike
        [300, 100, 340, 260],   # person standing alone at the kerb
        [400, 80, 700, 300],    # bus
        [420, 150, 460, 290],   # person standing in front of the bus (still a pedestrian)
    ], dtype=float)
    types = np.array(["person", "motorbike", "person", "bus", "person"], dtype=object)
    out = mark_riders(xyxy, types)
    assert list(out) == ["rider", "motorbike", "person", "bus", "person"]


def test_unsure_bus_is_not_counted_as_forty_people():
    import numpy as np
    from app.video.detector import demote_unsure_buses
    types = np.array(["bus", "bus", "car"], dtype=object)
    out = demote_unsure_buses(types, np.array([0.39, 0.82, 0.30]))
    assert list(out) == ["truck", "bus", "car"]


def test_roads_named_by_side_or_by_junction_names():
    import math
    from app.video.autozones import side_from_heading, zones_from_tracks
    assert side_from_heading(math.pi / 2) == "top"      # moving down the image = coming from the top
    assert side_from_heading(0.0) == "left"             # moving right = coming from the left
    # two streams: one moving right, one moving down
    tracks = {}
    for k in range(6):
        tracks[k] = [(50 + 20 * i, 300 + k * 3, 40, 30) for i in range(12)]
        tracks[100 + k] = [(400 + k * 3, 20 + 20 * i, 40, 30) for i in range(12)]
    roads = zones_from_tracks(tracks, 640, 480)
    assert sorted(r["side"] for r in roads) == ["left", "top"]
    assert sorted(r["name"] for r in roads) == ["From the left", "From the top"]
    named = zones_from_tracks(tracks, 640, 480, road_names={"left": "Agrabad Road", "top": "GEC Road"})
    assert sorted(r["name"] for r in named) == ["Agrabad Road", "GEC Road"]
