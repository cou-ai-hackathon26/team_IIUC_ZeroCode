"""People-first estimate: turn vehicle counts into people waiting.

people waiting on a road = sum over vehicle types of (count x average occupancy)

The occupancy numbers are ASSUMPTIONS (averages, not exact counts). They are
shown in the dashboard and the officer can edit them per junction.
"""
from __future__ import annotations

from app.config import DEFAULT_OCCUPANCY


def merged_occupancy(overrides: dict | None) -> dict[str, float]:
    """Default occupancy values with any junction-specific overrides applied."""
    occupancy = dict(DEFAULT_OCCUPANCY)
    for vtype, value in (overrides or {}).items():
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if vtype in occupancy and 0 <= value <= 200:
            occupancy[vtype] = value
    return occupancy


def people_for_counts(counts: dict[str, int], occupancy: dict[str, float]) -> tuple[float, dict[str, float]]:
    """Return (total people, people per vehicle type) for one road's vehicle counts."""
    by_type = {vtype: n * occupancy.get(vtype, occupancy["other"]) for vtype, n in counts.items()}
    return sum(by_type.values()), by_type


def add_people(road_stats: list[dict], occupancy: dict[str, float]) -> list[dict]:
    """Add 'people', 'people_by_type' and 'people_queued' to each road's stats (returns new dicts)."""
    result = []
    for road in road_stats:
        people, by_type = people_for_counts(road.get("vehicles", {}), occupancy)
        total = road.get("total_vehicles", 0)
        avg_per_vehicle = people / total if total else 0.0
        result.append({
            **road,
            "people": round(people, 1),
            "people_by_type": {k: round(v, 1) for k, v in by_type.items()},
            "people_per_vehicle": round(avg_per_vehicle, 2),
            "people_queued": round(road.get("queued", 0) * avg_per_vehicle, 1),
        })
    return result


def rank(roads: list[dict], by: str = "people") -> list[str]:
    """Road ids ordered from most to least (by 'people' or 'total_vehicles')."""
    return [r["id"] for r in sorted(roads, key=lambda r: r.get(by, 0), reverse=True)]
