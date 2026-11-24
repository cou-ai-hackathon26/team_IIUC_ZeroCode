"""Timing advisor: occupancy-weighted Max-Pressure.

Idea (from traffic-control research on "person-based" and Max-Pressure signal
control): give green time in proportion to how many PEOPLE are waiting, not
how many vehicles. Then apply simple safety rules:

- every road gets at least MIN_GREEN and at most MAX_GREEN seconds
- fairness guard: a road whose vehicles have waited longer than MAX_WAIT is served first
- pedestrian protection: many people waiting to cross -> extra walk time
- emergency (simulated only): the chosen road is served first with a long green
- low confidence (dark, rain, blocked camera): keep the existing fixed timer

The advisor only RECOMMENDS a plan. The traffic officer accepts or overrides it.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from app.config import CYCLE_SECONDS, MAX_GREEN, MAX_WAIT_SECONDS, MIN_GREEN

PEDESTRIAN_THRESHOLD = 8     # people waiting to cross before walk time is extended
BASE_WALK_SECONDS = 8
MAX_WALK_EXTENSION = 6
EMERGENCY_GREEN = 30
NO_TRAFFIC = "No vehicles in the road zones"
HOLD_SPLIT = "Holding the current split: counts are uncertain"
MEANINGFUL_CHANGE = 3        # seconds; smaller changes are reported as "keep current plan"


@dataclass
class AdvisorSettings:
    cycle: int = CYCLE_SECONDS
    min_green: int = MIN_GREEN
    max_green: int = MAX_GREEN
    max_wait: float = MAX_WAIT_SECONDS
    base_walk: int = BASE_WALK_SECONDS


@dataclass
class Advice:
    mode: str                                   # "advise" | "keep_fixed" | "emergency"
    plan: list[dict]                            # per road: id, name, index, green, fixed, delta, people, vehicles
    order: list[str]                            # road ids in the order they should get green
    walk_seconds: int
    walk_extension: int
    top: dict | None                            # the headline recommendation
    reasons: list[str] = field(default_factory=list)
    numbers: dict = field(default_factory=dict)  # values shown in the "Why?" panel
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode, "plan": self.plan, "order": self.order,
            "walk_seconds": self.walk_seconds, "walk_extension": self.walk_extension,
            "top": self.top, "reasons": self.reasons, "numbers": self.numbers,
            "created_at": self.created_at,
        }


def walk_extension(pedestrians_waiting: int) -> int:
    """Extra walk seconds: +2 s per 10 people waiting beyond the threshold, capped."""
    if pedestrians_waiting < PEDESTRIAN_THRESHOLD:
        return 0
    return min(MAX_WALK_EXTENSION, 2 * math.ceil(pedestrians_waiting / 10))


def split_green(pressures: list[float], total: int, min_green: int, max_green: int) -> list[int]:
    """Split `total` seconds between roads in proportion to pressure, within [min, max].

    Works by repeatedly fixing roads that hit a limit and sharing the rest.
    Returns whole seconds that add up exactly to `total` (when feasible).
    """
    n = len(pressures)
    if n == 0:
        return []
    total = max(total, n * min_green)
    weights = [max(p, 0.5) for p in pressures]  # tiny weight so empty roads still get min green
    green = [float(min_green)] * n
    free = list(range(n))
    remaining = total - n * min_green
    while free and remaining > 1e-9:
        share_total = sum(weights[i] for i in free)
        capped = []
        for i in free:
            extra = remaining * weights[i] / share_total
            room = max_green - green[i]
            if extra >= room:
                capped.append(i)
        if not capped:
            for i in free:
                green[i] += remaining * weights[i] / share_total
            remaining = 0
            break
        for i in capped:
            remaining -= max_green - green[i]
            green[i] = max_green
            free.remove(i)
    # round to whole seconds while keeping the exact total (largest remainder method)
    floors = [math.floor(g) for g in green]
    leftover = int(round(sum(green))) - sum(floors)
    order = sorted(range(n), key=lambda i: green[i] - floors[i], reverse=True)
    for i in order[:max(0, leftover)]:
        floors[i] += 1
    return floors


def advise(roads: list[dict], fixed_plan: dict[str, int], pedestrians_waiting: int = 0,
           confidence_level: str = "High", confidence_reasons: list[str] | None = None,
           emergency_road: str | None = None, settings: AdvisorSettings | None = None,
           careful: str | None = None) -> Advice:
    """Build a recommended plan from per-road stats (which must include 'people')."""
    s = settings or AdvisorSettings()
    fixed = {r["id"]: int(fixed_plan.get(r["id"], s.min_green)) for r in roads}
    ext = walk_extension(pedestrians_waiting)
    walk = s.base_walk + ext
    numbers = {
        "people": {r["id"]: r.get("people", 0) for r in roads},
        "vehicles": {r["id"]: r.get("total_vehicles", 0) for r in roads},
        "buses": {r["id"]: r.get("vehicles", {}).get("bus", 0) for r in roads},
        "longest_wait_s": {r["id"]: r.get("longest_wait_s", 0) for r in roads},
        "pedestrians_waiting": pedestrians_waiting,
        "cycle": s.cycle,
    }

    def plan_rows(greens: dict[str, int]) -> list[dict]:
        rows = []
        for idx, r in enumerate(roads, start=1):
            rows.append({
                "id": r["id"], "name": r.get("name", r["id"]), "index": idx,
                "green": greens[r["id"]], "fixed": fixed[r["id"]],
                "delta": greens[r["id"]] - fixed[r["id"]],
                "people": r.get("people", 0), "vehicles": r.get("total_vehicles", 0),
            })
        return rows

    if not roads:
        return Advice("keep_fixed", [], [], walk, ext, None, ["No roads found yet"], numbers)

    # 1. Low confidence -> do not guess, keep the existing fixed timer
    if confidence_level == "Low" and not emergency_road:
        reasons = ["Low confidence"] + list(confidence_reasons or [])
        return Advice("keep_fixed", plan_rows(fixed), [r["id"] for r in roads], s.base_walk, 0,
                      None, reasons, numbers)

    available = s.cycle - walk
    ids = [r["id"] for r in roads]
    pressures = [float(r.get("people", 0)) for r in roads]
    reasons: list[str] = []

    # 2. Emergency (simulated): chosen road gets a long green and goes first
    if emergency_road in ids:
        e_idx = ids.index(emergency_road)
        e_green = min(max(EMERGENCY_GREEN, s.min_green), s.max_green)
        others = [i for i in range(len(ids)) if i != e_idx]
        rest = split_green([pressures[i] for i in others], available - e_green, s.min_green, s.max_green)
        greens = {ids[e_idx]: e_green, **{ids[i]: g for i, g in zip(others, rest)}}
        order = [emergency_road] + [ids[i] for i in sorted(others, key=lambda i: pressures[i], reverse=True)]
        top = next(row for row in plan_rows(greens) if row["id"] == emergency_road)
        return Advice("emergency", plan_rows(greens), order, walk, ext, top, ["Emergency priority (simulated)"], numbers)

    # 3. Nothing to serve: never invent a reason to change the timer
    if sum(pressures) <= 0:
        return Advice("advise", plan_rows(fixed), ids, walk, ext, None, [NO_TRAFFIC], numbers)

    # 3b. Careful mode: the counts may be wrong (for example a bus or rickshaw partly hidden behind
    #     a truck in heavy rain). Never make the split tighter on uncertain counts: keep the current split.
    if careful:
        return Advice("advise", plan_rows(fixed), ids, walk, ext, None,
                      [HOLD_SPLIT, careful], numbers)

    # 4. Normal case: occupancy-weighted Max-Pressure split
    green_list = split_green(pressures, available, s.min_green, s.max_green)
    greens = dict(zip(ids, green_list))

    # 5. Fairness guard: roads waiting too long are served first
    overdue = [r["id"] for r in roads if r.get("longest_wait_s", 0) > s.max_wait]
    order = overdue + [i for i in sorted(ids, key=lambda i: pressures[ids.index(i)], reverse=True) if i not in overdue]
    if overdue:
        reasons.append("Fairness guard: " + ", ".join(overdue) + " waited longer than the limit")
    if ext:
        reasons.append(f"Pedestrian protection: +{ext} s walk time")

    rows = plan_rows(greens)
    # only a road where people are actually waiting can be told to get more green
    candidates = [row for row in rows if row["people"] > 0]
    best = max(candidates, key=lambda row: row["delta"]) if candidates else None
    if best and best["delta"] >= MEANINGFUL_CHANGE:
        top = best
    else:
        top = None
        reasons.append("Current plan already fits the traffic")
    return Advice("advise", rows, order, walk, ext, top, reasons, numbers)


def plan_for(roads: list[dict], fixed_plan: dict[str, int], changes: dict[str, float], minutes: int = 20,
             settings: AdvisorSettings | None = None) -> Advice:
    """Green split for the next `minutes` when the crowd is expected to change on one or more roads.

    `changes` = {road id: change}, e.g. {"R2": 1.0} means Road 2's crowd grows to double,
    {"R1": -0.5} means Road 1's crowd falls by half. Any road, any length of time.

    Each road's demand = people arriving per minute (from tracking), or the people waiting now if
    there is no tracking history yet. A change happens step by step over the period, so on
    average a road has (1 + change / 2) times today's demand. The split then uses the same rules
    as normal advice: 10 to 60 s per road, yellow untouched.
    """
    s = settings or AdvisorSettings()
    changes = {rid: max(-0.9, min(5.0, float(g))) for rid, g in changes.items()}
    demand_roads = []
    for r in roads:
        rate = float(r.get("arrivals_per_min", 0)) * float(r.get("people_per_vehicle") or 1.0)
        demand = rate if rate > 0 else float(r.get("people", 0))
        if r["id"] in changes:
            demand = max(demand, 1.0) * (1 + changes[r["id"]] / 2)
        demand_roads.append({**r, "people_now": r.get("people", 0), "people": round(demand, 1)})
    advice = advise(demand_roads, fixed_plan, settings=s)
    rows = advice.plan
    # follow the officer's direction: a road that will get busier never loses green, a road that
    # will get emptier never gains green (the camera's arrival counts can be noisy)
    for row in rows:
        g = changes.get(row["id"])
        if g is not None and ((g > 0 and row["green"] < row["fixed"]) or (g < 0 and row["green"] > row["fixed"])):
            row["green"], row["delta"] = row["fixed"], 0
    if any(g < 0 for g in changes.values()):
        # time freed by an emptier road goes to the roads with the most people waiting
        freed = sum(row["fixed"] - row["green"] for row in rows if changes.get(row["id"], 0) < 0)
        if freed <= 0:
            for row in rows:
                if changes.get(row["id"], 0) < 0:
                    row["green"] = max(s.min_green, round(row["fixed"] * (1 + changes[row["id"]] / 2)))
                    row["delta"] = row["green"] - row["fixed"]
            freed = sum(row["fixed"] - row["green"] for row in rows if changes.get(row["id"], 0) < 0)
        others = sorted([row for row in rows if changes.get(row["id"], 0) >= 0], key=lambda r: -r["people"])
        for row in others:
            if freed <= 0:
                break
            add = min(freed, s.max_green - row["green"])
            if row["delta"] < 0:
                add = min(add + 0, s.max_green - row["green"])
            row["green"] += add
            row["delta"] = row["green"] - row["fixed"]
            freed -= add
    main = max(changes, key=lambda rid: changes[rid]) if changes else None   # the road with the biggest rush
    top = next((row for row in rows if row["id"] == main), None)
    if top is not None and changes[main] > 0 and top["delta"] < MEANINGFUL_CHANGE:
        # the rush road never loses green in its own rush plan: if it needs no more, keep today's split
        for row in rows:
            row["green"], row["delta"] = row["fixed"], 0
        top = next((row for row in rows if row["id"] == main), None)
    advice.mode = "plan_ahead"
    advice.top = top
    names = {r["id"]: r.get("name", r["id"]) for r in roads}
    advice.reasons = [f"Crowd change over {minutes} min: " +
                      ", ".join(f"{names.get(rid, rid)} {int(g * 100):+d}%" for rid, g in changes.items())]
    advice.numbers["plan_minutes"] = minutes
    advice.numbers["rush_growth_percent"] = int(changes.get(main, 0) * 100) if main else 0
    advice.numbers["changes_percent"] = {rid: int(g * 100) for rid, g in changes.items()}
    advice.numbers["demand_per_min"] = {r["id"]: r["people"] for r in demand_roads}
    return advice


def plan_ahead(roads: list[dict], fixed_plan: dict[str, int], rush_road: str, growth: float,
               minutes: int = 20, settings: AdvisorSettings | None = None) -> Advice:
    """One road's rush (the 📅 button): the same as plan_for with one road."""
    return plan_for(roads, fixed_plan, {rush_road: growth}, minutes, settings)


def queue_forecast(roads: list[dict], rows: list[dict], changes: dict[str, float] | str, growth: float | None = None,
                   minutes: int = 20, cycle: int = 120) -> dict:
    """People left waiting after `minutes`, with the normal timer and with the plan.

    Simple and explainable: today the timer just about keeps up with the people who come each
    cycle (the people waiting now). On a changing road, arrivals change step by step up to
    (1 + change). A road clears people in proportion to its green time, so more green clears more.
    """
    if isinstance(changes, str):            # old call: (rush_road, growth)
        changes = {changes: float(growth or 0)}
    per_min = {r["id"]: max(float(r.get("people", 0)), 1.0) / (cycle / 60) for r in roads}
    green = {row["id"]: row["green"] for row in rows}
    fixed = {row["id"]: max(row["fixed"], 1) for row in rows}
    out = {}
    for r in roads:
        rid, start = r["id"], float(r.get("people", 0))
        q_fixed = q_plan = start
        g = changes.get(rid, 0.0)
        for m in range(minutes):
            arrive = per_min[rid] * (1 + g * (m + 1) / minutes)
            q_fixed = max(0.0, q_fixed + arrive - per_min[rid])
            q_plan = max(0.0, q_plan + arrive - per_min[rid] * green.get(rid, fixed[rid]) / fixed[rid])
        out[rid] = {"now": round(start), "fixed": round(q_fixed), "plan": round(q_plan)}
    growing = [rid for rid in changes if changes[rid] > 0]
    main = max(growing, key=lambda rid: changes[rid]) if growing else None   # the busiest-growing road
    rush = out.get(main, {"now": 0, "fixed": 0, "plan": 0})
    # even the longest green cannot stop a growing line -> the lights alone are not enough
    too_big = any(changes.get(rid, 0) > 0 and green.get(rid, 0) >= 60 and q["plan"] > max(2 * q["now"], q["now"] + 30)
                  for rid, q in out.items())
    return {"roads": out, "rush": rush, "main": main, "too_big": too_big}
