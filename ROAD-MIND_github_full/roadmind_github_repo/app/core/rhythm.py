"""Bangladeshi rhythm mode: forecast the next 30 minutes.

forecast = seasonal baseline x local-event multiplier

- Seasonal baseline: average people waiting recorded at the same kind of day
  (Friday / other days) and time of day (+-15 min), from counts the app saves
  every minute and from clips processed with scripts/record_counts.py.
  With too little history it falls back to the last 15 minutes.
- Events: config/events.json lists Jumu'ah, school release, market hours and
  Eid rush windows with multipliers. Default multipliers are ASSUMPTIONS until
  enough recorded counts exist to replace them.
- Uncertainty band: spread of the history, or +-30% when history is thin.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from app.config import ROOT

TZ = ZoneInfo("Asia/Dhaka")
HORIZON_MIN = 30
STEP_MIN = 5
RUSH_RATIO = 1.15  # forecast this much above now -> show "rush expected" banner


def now_local() -> datetime:
    return datetime.now(TZ)


def load_events() -> list[dict]:
    path = ROOT / "config" / "events.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("events", [])


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def active_events(when: datetime, events: list[dict]) -> list[dict]:
    """Events whose day and time window include `when`."""
    found = []
    minute = when.hour * 60 + when.minute
    weekday = when.strftime("%a")  # Mon, Tue, ...
    date = when.strftime("%Y-%m-%d")
    for ev in events:
        if ev.get("days") and weekday not in ev["days"]:
            continue
        if "dates" in ev and date not in ev["dates"]:
            continue  # date-limited event (an empty list means it is not scheduled yet)
        if _minutes(ev["start"]) <= minute < _minutes(ev["end"]):
            found.append(ev)
    return found


def day_kind(when: datetime) -> str:
    return "friday" if when.weekday() == 4 else "other"


def forecast(history: list[dict], current_people: float, when: datetime | None = None,
             events: list[dict] | None = None) -> dict:
    """history items: {'ts': ISO time, 'day_kind': str, 'minute': int, 'people': float} (junction totals)."""
    when = when or now_local()
    events = load_events() if events is None else events
    recent_cut = when - timedelta(minutes=15)
    recent = [h["people"] for h in history if datetime.fromisoformat(h["ts"]) >= recent_cut]
    fallback = float(np.mean(recent)) if recent else float(current_people)

    points, banner = [], None
    for k in range(0, HORIZON_MIN + 1, STEP_MIN):
        t = when + timedelta(minutes=k)
        minute = t.hour * 60 + t.minute
        same = [h["people"] for h in history
                if h["day_kind"] == day_kind(t) and abs(h["minute"] - minute) <= 15]
        if len(same) >= 3:
            base, spread, source = float(np.mean(same)), float(np.std(same)), "history"
        else:
            base, spread, source = fallback, 0.3 * fallback, "recent"
        evs = active_events(t, events)
        mult = float(np.prod([e.get("multiplier", 1.0) for e in evs])) if evs else 1.0
        value = base * mult
        points.append({
            "minutes_ahead": k, "time": t.strftime("%H:%M"),
            "people": round(value, 1), "low": round(max(0.0, value - spread), 1),
            "high": round(value + spread, 1), "events": [e["name"] for e in evs], "source": source,
        })
        if banner is None and k > 0 and evs and value >= RUSH_RATIO * max(points[0]["people"], 1):
            banner = {"minutes": k, "event": evs[0]["name"], "event_bn": evs[0].get("name_bn", evs[0]["name"])}

    return {
        "now": when.strftime("%a %H:%M"),
        "points": points,
        "banner": banner,
        "history_points": len(history),
        "note": "Forecast from recorded counts and an event calendar; multipliers are assumptions until enough data is recorded.",
    }
