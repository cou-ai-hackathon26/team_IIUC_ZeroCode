"""The connected lights change only when the officer accepts or overrides."""
from app.pipeline import JunctionPipeline


def _pipeline():
    junction = {"id": "t", "name": "T", "source": "", "cycle_seconds": 120,
                "roads": [{"id": "R1", "name": "Road 1", "polygon": [[0, 0], [1, 0], [1, 1]]},
                          {"id": "R2", "name": "Road 2", "polygon": [[0, 0], [1, 0], [0, 1]]}],
                "crossings": [], "fixed_plan": {"R1": 40, "R2": 40}}
    return JunctionPipeline(junction)


ADVICE = {"plan": [{"id": "R1", "green": 60, "fixed": 40}, {"id": "R2", "green": 30, "fixed": 40}],
          "order": ["R1", "R2"], "top": {"id": "R1", "green": 60, "fixed": 40}}


def test_starts_on_fixed_plan():
    s = _pipeline().signal_state()
    assert s["source"] == "fixed" and s["plan"] == {"R1": 40, "R2": 40} and s["yellow"] == 3


def test_accept_applies_the_advice():
    p = _pipeline()
    p.apply_decision({"status": "accepted", "advice": ADVICE})
    s = p.signal_state()
    assert s["source"] == "accepted" and s["plan"] == {"R1": 60, "R2": 30} and s["order"][0] == "R1"


def test_override_uses_the_officers_seconds_within_limits():
    p = _pipeline()
    p.apply_decision({"status": "overridden", "chosen_seconds": 10, "advice": ADVICE})
    assert p.signal_state()["plan"] == {"R1": 50, "R2": 40}
    p.apply_decision({"status": "overridden", "chosen_seconds": 99, "advice": ADVICE})
    assert p.signal_state()["plan"]["R1"] == 60     # never above the maximum green


def test_emergency_goes_first_and_cancel_restores():
    p = _pipeline()
    p.start_emergency("R2")
    s = p.signal_state()
    assert s["source"] == "emergency" and s["order"][0] == "R2"
    p.cancel_emergency()
    assert p.signal_state()["source"] == "fixed"


def test_an_advice_can_be_decided_only_once(tmp_path, monkeypatch):
    import app.db as db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(db, "_conn", None)
    did = db.add_decision("t", {"mode": "advise", "plan": []}, {"bn": "", "en": ""}, None)
    assert db.decide(did, "accept", 5, None)["status"] == "accepted"
    assert db.decide(did, "override", 5, "Other").get("already_decided") is True
