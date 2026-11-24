"""Unit tests for the people estimate, advisor and explanation modules."""
from app.core.advisor import AdvisorSettings, advise, split_green, walk_extension
from app.core.explain import bn, template_texts, validate
from app.core.people import add_people, merged_occupancy, rank

OCC = merged_occupancy({})


def road(rid, vehicles, wait=0.0):
    total = sum(vehicles.values())
    return {"id": rid, "name": rid, "vehicles": vehicles, "total_vehicles": total,
            "queued": total, "longest_wait_s": wait}


# --- people estimate -------------------------------------------------------
def test_buses_outweigh_cars():
    roads = add_people([road("R1", {"car": 12}), road("R2", {"bus": 3, "car": 6})], OCC)
    assert rank(roads, "total_vehicles")[0] == "R1"   # more vehicles on R1 ...
    assert rank(roads, "people")[0] == "R2"           # ... but more PEOPLE on R2


def test_occupancy_override_and_bad_values_ignored():
    occ = merged_occupancy({"bus": 50, "car": "abc", "spaceship": 3, "cng": -4})
    assert occ["bus"] == 50 and occ["car"] == OCC["car"] and "spaceship" not in occ and occ["cng"] == OCC["cng"]


# --- advisor ---------------------------------------------------------------
def test_split_respects_limits_and_total():
    greens = split_green([100, 1, 1, 1], total=110, min_green=10, max_green=60)
    assert sum(greens) == 110
    assert all(10 <= g <= 60 for g in greens)
    assert greens[0] == 60


def test_people_first_recommendation():
    roads = add_people([road("R1", {"car": 12}), road("R2", {"bus": 3, "car": 6})], OCC)
    a = advise(roads, {"R1": 56, "R2": 56}, settings=AdvisorSettings(cycle=120))
    assert a.mode == "advise"
    assert a.top["id"] == "R2" and a.top["delta"] > 0
    assert sum(r["green"] for r in a.plan) + a.walk_seconds == 120


def test_low_confidence_keeps_fixed_timer():
    roads = add_people([road("R1", {"car": 3}), road("R2", {"bus": 2})], OCC)
    a = advise(roads, {"R1": 50, "R2": 50}, confidence_level="Low", confidence_reasons=["Dark"])
    assert a.mode == "keep_fixed" and a.top is None
    assert [r["green"] for r in a.plan] == [50, 50]
    assert "Dark" in a.reasons


def test_fairness_guard_serves_overdue_road_first():
    roads = add_people([road("R1", {"bus": 3}), road("R2", {"car": 1}, wait=200)], OCC)
    a = advise(roads, {"R1": 50, "R2": 50})
    assert a.order[0] == "R2"
    assert any("Fairness" in r for r in a.reasons)


def test_pedestrian_extension_and_emergency():
    assert walk_extension(3) == 0 and walk_extension(22) == 6
    roads = add_people([road("R1", {"bus": 3}), road("R2", {"car": 1})], OCC)
    a = advise(roads, {"R1": 50, "R2": 50}, emergency_road="R2")
    assert a.mode == "emergency" and a.order[0] == "R2" and a.top["id"] == "R2"


# --- explanation -----------------------------------------------------------
def test_bangla_template_and_validation():
    roads = add_people([road("R1", {"car": 12}), road("R2", {"bus": 3, "car": 6})], OCC)
    advice = advise(roads, {"R1": 56, "R2": 56}).to_dict()
    text_bn, text_en = template_texts(advice)
    delta = advice["top"]["delta"]
    assert bn(2) in text_bn and bn(delta) in text_bn and str(delta) in text_en
    assert validate(text_bn, advice)
    assert not validate("রোড ৩-এ সবুজ বাতি দিন।", advice)   # wrong numbers are rejected
    assert bn(15) == "১৫"


def test_no_traffic_means_no_change():
    from app.core.advisor import advise
    from app.core.explain import template_texts
    roads = [{"id": f"R{i}", "name": f"Road {i}", "people": 0, "total_vehicles": 0} for i in range(1, 5)]
    a = advise(roads, {"R1": 30, "R2": 30, "R3": 25, "R4": 25})
    assert a.top is None
    assert all(row["delta"] == 0 for row in a.plan)
    assert "No vehicles" in template_texts(a.__dict__)[1]


def test_voice_returns_none_without_service(monkeypatch, tmp_path):
    import asyncio, sys, types
    from app.core import voice
    monkeypatch.setattr(voice, "VOICE_DIR", tmp_path)
    broken = types.SimpleNamespace(Communicate=lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setitem(sys.modules, "edge_tts", broken)
    assert asyncio.run(voice.speech_mp3("রোড ১", "bn")) is None
    assert asyncio.run(voice.speech_mp3("", "bn")) is None
