"""Ask Roadmind: understanding the question offline (no Gemini key)."""
from app.core.chat import is_bangla, understand_by_rules

ROADS = [{"id": "R1", "name": "Station Road"}, {"id": "R2", "name": "College Road"}]


def test_bangla_festival_question_becomes_a_plan():
    q = understand_by_rules("রোড ২-এ উৎসবের ভিড় আসছে, পরের ৩০ মিনিট কী করব?", ROADS)
    assert q["intent"] == "plan" and q["road_id"] == "R2" and q["minutes"] == 30


def test_banglish_and_road_name_and_double():
    q = understand_by_rules("college road e mela, bhir double hobe", ROADS)
    assert q["intent"] == "plan" and q["road_id"] == "R2" and q["growth"] == 1.0
    assert is_bangla("college road e mela, bhir double hobe")


def test_english_percent_and_status_and_why():
    q = understand_by_rules("Eid rush on road 1, +80% for an hour", ROADS)
    assert q["road_id"] == "R1" and q["growth"] == 0.8 and q["minutes"] == 60
    assert understand_by_rules("How many people are waiting now?", ROADS)["intent"] == "status"
    assert understand_by_rules("why this advice?", ROADS)["intent"] == "why"
    assert understand_by_rules("বৃষ্টিতে কী করব", ROADS)["intent"] == "rain"


def test_several_roads_any_time_and_a_falling_crowd():
    roads = ROADS + [{"id": "R3", "name": "Bazar Road"}]
    q = understand_by_rules("অফিস ছুটির পর রোড ১ আর ৩-এ ভিড় বাড়বে, দুই ঘণ্টার প্ল্যান দাও", roads)
    assert q["intent"] == "plan" and q["road_ids"] == ["R1", "R3"] and q["minutes"] == 120
    q = understand_by_rules("road 2 faka hoye jabe, 45 min", roads)
    assert q["intent"] == "plan" and q["growth"] < 0 and q["minutes"] == 45


def test_gemini_numbers_must_come_from_roadmind():
    from app.core.chat import numbers_ok
    facts = '{"green": [{"road": 2, "now_s": 40, "plan_s": 57}], "stuck": 132}'
    assert numbers_ok("রোড ২-এ সবুজ ৪০ থেকে ৫৭ সেকেন্ড, আটকে থাকবে ১৩২ জন", facts)
    assert not numbers_ok("রোড ২-এ সবুজ ৭৫ সেকেন্ড দিন", facts)       # 75 is made up -> dropped


def test_plan_for_several_roads():
    from app.core.advisor import plan_for
    roads = [{"id": i, "name": i, "people": 30, "vehicles": {}} for i in ("R1", "R2", "R3")]
    a = plan_for(roads, {"R1": 30, "R2": 30, "R3": 30}, {"R1": 1.0, "R3": 1.0}, minutes=90)
    green = {r["id"]: r["green"] for r in a.plan}
    assert green["R1"] > green["R2"] and green["R3"] > green["R2"] and a.numbers["plan_minutes"] == 90
