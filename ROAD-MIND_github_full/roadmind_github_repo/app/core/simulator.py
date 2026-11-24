"""A small queue simulator: what would happen with the fixed timer vs Roadmind's plan?

Everything here is SIMULATED and labelled as such in the UI. It shows what the
advice could do; it is not proof of real-world savings.

Model (1-second steps, per road):
- vehicles arrive at the rate measured from the video (random, same seed for both plans)
- during that road's green, vehicles leave at a fixed saturation flow
- each vehicle carries the road's average people per vehicle (from the people estimate)

Metrics: average vehicle wait, average PERSON wait (person delay), people moved
per minute, and the longest wait.
"""
from __future__ import annotations

from collections import deque

import numpy as np

SATURATION_FLOW = 0.6   # vehicles per second leaving one approach during green (mixed traffic)
SIM_SECONDS = 600
PREVIEW_SECONDS = 120


def _phases(order: list[str], greens: dict[str, int], walk: int) -> list[tuple[str | None, int]]:
    phases = [(rid, int(greens[rid])) for rid in order if greens.get(rid, 0) > 0]
    if walk > 0:
        phases.append((None, int(walk)))  # all-red pedestrian phase
    return phases


def _run(roads: list[dict], order: list[str], greens: dict[str, int], walk: int, seconds: int,
         arrivals: dict[str, np.ndarray], sample_every: int = 0) -> dict:
    queues = {r["id"]: deque(-float(w) for w in r.get("initial_waits", [])) for r in roads}
    ppv = {r["id"]: r["ppv"] for r in roads}
    phases = _phases(order, greens, walk)
    cycle = sum(d for _, d in phases) or 1
    served_wait_veh, served_wait_people, served_people = 0.0, 0.0, 0.0
    served_count, max_wait = 0, 0.0
    flow_credit = {rid: 0.0 for rid in queues}
    series = []

    for t in range(seconds):
        # which road is green at second t?
        pos, green_road = t % cycle, None
        for rid, dur in phases:
            if pos < dur:
                green_road = rid
                break
            pos -= dur
        for rid in queues:
            for _ in range(int(arrivals[rid][t])):
                queues[rid].append(float(t))
        if green_road is not None:
            flow_credit[green_road] += SATURATION_FLOW
            while flow_credit[green_road] >= 1 and queues[green_road]:
                arrived = queues[green_road].popleft()
                wait = t - arrived
                served_count += 1
                served_wait_veh += wait
                served_wait_people += wait * ppv[green_road]
                served_people += ppv[green_road]
                max_wait = max(max_wait, wait)
                flow_credit[green_road] -= 1
            if not queues[green_road]:
                flow_credit[green_road] = 0.0
        if sample_every and t % sample_every == 0:
            series.append(round(sum(len(q) * ppv[rid] for rid, q in queues.items()), 1))

    # vehicles still waiting at the end also count, so a plan cannot "hide" queues
    left_veh = sum(len(q) for q in queues.values())
    left_wait_veh = sum(seconds - a for q in queues.values() for a in q)
    left_wait_people = sum((seconds - a) * ppv[rid] for rid, q in queues.items() for a in q)
    left_people = sum(len(q) * ppv[rid] for rid, q in queues.items())
    for q in queues.values():
        if q:
            max_wait = max(max_wait, seconds - q[0])
    total_veh = served_count + left_veh
    total_people = served_people + left_people
    return {
        "avg_wait_s": round((served_wait_veh + left_wait_veh) / total_veh, 1) if total_veh else 0.0,
        "avg_person_wait_s": round((served_wait_people + left_wait_people) / total_people, 1) if total_people else 0.0,
        "people_moved_per_min": round(served_people / (seconds / 60), 1),
        "max_wait_s": round(max_wait, 1),
        "series": series,
    }


def compare(roads: list[dict], fixed_greens: dict[str, int], fixed_walk: int,
            plan_order: list[str], plan_greens: dict[str, int], plan_walk: int, seed: int = 7) -> dict:
    """Simulate fixed timer vs Roadmind plan on identical arrivals.

    `roads` items need: id, arrival_rate (vehicles/s), ppv (people per vehicle),
    initial_waits (list of seconds already waited by queued vehicles).
    """
    rng = np.random.default_rng(seed)
    arrivals = {r["id"]: rng.poisson(max(r["arrival_rate"], 0.0), SIM_SECONDS) for r in roads}
    fixed_order = [r["id"] for r in roads]
    fixed = _run(roads, fixed_order, fixed_greens, fixed_walk, SIM_SECONDS, arrivals)
    smart = _run(roads, plan_order, plan_greens, plan_walk, SIM_SECONDS, arrivals)
    pf = _run(roads, fixed_order, fixed_greens, fixed_walk, PREVIEW_SECONDS, arrivals, sample_every=5)
    ps = _run(roads, plan_order, plan_greens, plan_walk, PREVIEW_SECONDS, arrivals, sample_every=5)
    change = (smart["avg_person_wait_s"] - fixed["avg_person_wait_s"]) / fixed["avg_person_wait_s"] * 100 \
        if fixed["avg_person_wait_s"] else 0.0
    for d in (fixed, smart):
        d.pop("series")
    return {
        "label": "simulated",
        "seconds": SIM_SECONDS,
        "fixed": fixed,
        "roadmind": smart,
        "person_wait_change_pct": round(change, 1),
        "preview": {"t": list(range(0, PREVIEW_SECONDS, 5)), "fixed": pf["series"], "roadmind": ps["series"]},
    }
