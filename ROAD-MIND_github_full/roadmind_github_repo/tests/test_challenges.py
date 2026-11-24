"""On-site challenges: a 20-minute rush plan, and no tighter split when vehicles hide in heavy rain."""
import numpy as np

from app.core.advisor import HOLD_SPLIT, advise, plan_ahead
from app.video.tracker import hidden_behind_trucks
from tests.test_signal import _pipeline

ROADS = [
    {"id": "R1", "name": "Road 1", "people": 30, "vehicles": {"car": 10}, "total_vehicles": 10, "wait_s": 20, "arrivals_per_min": 6, "people_per_vehicle": 3},
    {"id": "R2", "name": "Road 2", "people": 30, "vehicles": {"car": 10}, "total_vehicles": 10, "wait_s": 20, "arrivals_per_min": 6, "people_per_vehicle": 3},
]
FIXED = {"R1": 40, "R2": 40}


def test_plan_ahead_gives_the_rush_road_more_green():
    a = plan_ahead(ROADS, FIXED, "R1", growth=1.0, minutes=20)
    assert a.mode == "plan_ahead" and a.top["id"] == "R1" and a.top["delta"] > 0
    assert a.numbers["plan_minutes"] == 20
    assert all(10 <= r["green"] <= 60 for r in a.plan)


def test_hidden_vehicles_in_rain_hold_the_split():
    roads = [{**ROADS[0], "people": 80}, ROADS[1]]
    full = {"R1": 55, "R2": 55}                                # the whole cycle is in use
    normal = advise(roads, full)
    assert any(r["delta"] < 0 for r in normal.plan)          # normally Road 2 would be cut
    careful = advise(roads, full, careful="Heavy rain: a bus may be hidden behind a truck")
    assert all(r["delta"] == 0 for r in careful.plan) and HOLD_SPLIT in careful.reasons


def test_box_behind_a_truck_is_counted_as_partly_hidden():
    boxes = np.array([[0, 0, 100, 100], [80, 10, 140, 60], [300, 300, 340, 340]], dtype=float)
    covers = hidden_behind_trucks(boxes, ["truck", "rickshaw", "car"])
    assert covers.tolist() == [1, 0, 0]


def test_rain_with_a_truck_is_a_risk_but_dry_weather_is_not():
    p = _pipeline()
    roads = [{**ROADS[0], "trucks": 1, "partly_hidden": 1}, ROADS[1]]
    assert p.hidden_risk(roads, {"reasons": []}) is None
    p.set_rain(True)
    assert "Road 1" in p.hidden_risk(roads, {"reasons": []})
    p.set_rain(False)
    assert p.hidden_risk(roads, {"reasons": ["Blur / rain"]}) is not None   # blur found by the camera check


def test_accepted_rush_plan_runs_then_lights_go_back(monkeypatch):
    p = _pipeline()
    plan = {"mode": "plan_ahead", "numbers": {"plan_minutes": 20}, "order": ["R1", "R2"],
            "plan": [{"id": "R1", "green": 55, "fixed": 40}, {"id": "R2", "green": 30, "fixed": 40}],
            "top": {"id": "R1", "green": 55, "fixed": 40}}
    p.apply_decision({"status": "accepted", "advice": plan})
    s = p.signal_state()
    assert s["source"] == "plan_ahead" and s["plan"]["R1"] == 55 and p._plan_until is not None
    assert p._signal_before_plan["source"] == "fixed"


def test_rush_road_never_loses_green_in_its_own_plan():
    roads = [{**ROADS[0], "people": 2, "arrivals_per_min": 0.2}, {**ROADS[1], "people": 90, "arrivals_per_min": 20}]
    a = plan_ahead(roads, {"R1": 55, "R2": 55}, "R1", growth=0.3)
    assert all(r["delta"] == 0 for r in a.plan)


def test_queue_forecast_plan_beats_normal_timer():
    from app.core.advisor import queue_forecast
    a = plan_ahead(ROADS, {"R1": 55, "R2": 55}, "R2", growth=1.0, minutes=20)
    fc = queue_forecast(ROADS, a.plan, "R2", 1.0, 20)
    assert fc["rush"]["plan"] < fc["rush"]["fixed"]
