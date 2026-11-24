"""Tests for the confidence check, simulator and rhythm forecast."""
from datetime import datetime

import cv2
import numpy as np

from app.core.rhythm import TZ, active_events, forecast, load_events
from app.core.simulator import compare
from app.video.confidence import ConfidenceChecker


def _scene():
    rng = np.random.default_rng(0)
    img = rng.integers(60, 200, (540, 960, 3), dtype=np.uint8)
    for i in range(0, 960, 40):
        cv2.line(img, (i, 0), (i, 540), (255, 255, 255), 2)
    return img


def _settle(checker, frame, n=8, dets=6, conf=0.8):
    for _ in range(n):
        out = checker.update(frame, dets, conf)
    return out


def test_confidence_levels():
    assert _settle(ConfidenceChecker(), _scene())["level"] == "High"
    dark = (_scene() * 0.15).astype(np.uint8)
    out = _settle(ConfidenceChecker(), dark)
    assert "Dark" in out["reasons"]
    blocked = np.full((540, 960, 3), 30, np.uint8)  # a hand over the lens
    out = _settle(ConfidenceChecker(), blocked, dets=0, conf=None)
    assert out["level"] == "Low" and "View blocked" in out["reasons"]


def test_simulator_people_first_helps_bus_road():
    roads = [
        {"id": "R1", "arrival_rate": 0.25, "ppv": 1.5, "initial_waits": [20] * 8},
        {"id": "R2", "arrival_rate": 0.18, "ppv": 12.0, "initial_waits": [20] * 6},
    ]
    out = compare(roads, {"R1": 56, "R2": 56}, 8, ["R2", "R1"], {"R1": 40, "R2": 72}, 8)
    assert out["label"] == "simulated"
    assert out["roadmind"]["avg_person_wait_s"] < out["fixed"]["avg_person_wait_s"]
    assert len(out["preview"]["fixed"]) == len(out["preview"]["t"])


def test_rhythm_friday_jumuah_banner():
    events = load_events()
    fri_noon = datetime(2026, 11, 27, 12, 10, tzinfo=TZ)  # a Friday
    assert not active_events(fri_noon, events)
    out = forecast([], current_people=100, when=fri_noon, events=events)
    assert out["banner"] and "Jumu" in out["banner"]["event"]
    assert out["points"][0]["people"] == 100
