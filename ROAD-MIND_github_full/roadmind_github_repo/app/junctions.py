"""Load and save junction settings (junctions/<id>.json).

Each junction file holds: name, video source, road zones, crossing zones,
the existing fixed-timer plan and any occupancy overrides.
"""
from __future__ import annotations

import json
import re

from app.config import JUNCTIONS_DIR

ID_PATTERN = re.compile(r"^[a-z0-9_-]{1,40}$")


def valid_id(junction_id: str) -> bool:
    return bool(ID_PATTERN.match(junction_id))


def list_junctions() -> list[dict]:
    items = []
    for path in sorted(JUNCTIONS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items.append({"id": path.stem, "name": data.get("name", path.stem)})
    return items


def load_junction(junction_id: str) -> dict:
    if not valid_id(junction_id):
        raise ValueError("Invalid junction id")
    path = JUNCTIONS_DIR / f"{junction_id}.json"
    if not path.exists():
        raise FileNotFoundError(junction_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["id"] = junction_id
    data.setdefault("roads", [])
    data.setdefault("crossings", [])
    data.setdefault("occupancy", {})
    return data


def _clean_polygon(points: list) -> list[list[float]]:
    cleaned = []
    for p in points:
        x, y = float(p[0]), float(p[1])
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("Polygon points must be between 0 and 1")
        cleaned.append([round(x, 4), round(y, 4)])
    if cleaned and len(cleaned) < 3:
        raise ValueError("A zone needs at least 3 points")
    return cleaned


def _clean_zones(items: list[dict], prefix: str) -> list[dict]:
    zones = []
    for i, item in enumerate(items, start=1):
        zone_id = str(item.get("id") or f"{prefix}{i}")
        if not re.match(r"^[A-Za-z0-9_-]{1,20}$", zone_id):
            raise ValueError(f"Invalid zone id: {zone_id}")
        zones.append({
            "id": zone_id,
            "name": str(item.get("name") or zone_id)[:40],
            "polygon": _clean_polygon(item.get("polygon", [])),
        })
    return zones


def save_junction(junction_id: str, updates: dict) -> dict:
    """Merge validated updates into the junction file and save it."""
    if not valid_id(junction_id):
        raise ValueError("Invalid junction id")
    path = JUNCTIONS_DIR / f"{junction_id}.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if "name" in updates:
        data["name"] = str(updates["name"])[:60]
    if "source" in updates:
        data["source"] = str(updates["source"])[:300]
    if "roads" in updates:
        data["roads"] = _clean_zones(updates["roads"], "R")
    if "crossings" in updates:
        data["crossings"] = _clean_zones(updates["crossings"], "C")
    if "occupancy" in updates:
        occ = {}
        for vtype, value in dict(updates["occupancy"]).items():
            value = float(value)
            if not 0 <= value <= 200:
                raise ValueError("Occupancy must be between 0 and 200")
            occ[str(vtype)[:30]] = round(value, 2)
        data["occupancy"] = occ
    if "fixed_plan" in updates:
        plan = {str(k)[:20]: int(v) for k, v in dict(updates["fixed_plan"]).items()}
        if any(not 0 <= v <= 300 for v in plan.values()):
            raise ValueError("Fixed plan seconds must be between 0 and 300")
        data["fixed_plan"] = plan
    if "cycle_seconds" in updates:
        cycle = int(updates["cycle_seconds"])
        if not 30 <= cycle <= 300:
            raise ValueError("Cycle must be between 30 and 300 seconds")
        data["cycle_seconds"] = cycle
    data.pop("id", None)
    JUNCTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return load_junction(junction_id)
