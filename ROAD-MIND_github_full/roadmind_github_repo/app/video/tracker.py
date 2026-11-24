"""Tracking, road zones and queues.

1. ByteTrack (run inside the detector) gives every vehicle a stable ID across frames.
2. Each road has a polygon zone (drawn on the calibration page) near its stop line.
3. For every road we count vehicles by type, how many are stopped (the queue),
   and how long the longest-waiting vehicle has been stopped.
4. Crossing zones count pedestrians waiting to cross.

Zone polygons are stored as fractions of the frame (0..1), so they work at any
video resolution.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np
import supervision as sv

from app.config import STOPPED_SPEED_PX_S, TRACK_HISTORY_SECONDS
from app.video.detector import VEHICLE_TYPES

ANCHOR = sv.Position.BOTTOM_CENTER  # where a vehicle touches the road


@dataclass
class Zone:
    id: str
    name: str
    polygon: list[list[float]]  # normalised [[x, y], ...]
    _zone: sv.PolygonZone | None = field(default=None, repr=False)
    _size: tuple[int, int] | None = field(default=None, repr=False)

    def pixel_polygon(self, width: int, height: int) -> np.ndarray:
        return np.array([[x * width, y * height] for x, y in self.polygon], dtype=np.int32)

    def trigger(self, detections: sv.Detections, width: int, height: int) -> np.ndarray:
        """Boolean mask: which detections have their anchor inside this zone."""
        if len(self.polygon) < 3 or len(detections) == 0:
            return np.zeros(len(detections), dtype=bool)
        if self._zone is None or self._size != (width, height):
            self._zone = sv.PolygonZone(self.pixel_polygon(width, height), triggering_anchors=(ANCHOR,))
            self._size = (width, height)
        return self._zone.trigger(detections)


def zones_from_config(items: list[dict]) -> list[Zone]:
    return [Zone(id=i["id"], name=i.get("name", i["id"]), polygon=i.get("polygon", [])) for i in items]


HIDE_OVERLAP = 0.20   # a box at least 20% covered by a truck counts as partly hidden


def hidden_behind_trucks(xyxy: np.ndarray, types: np.ndarray) -> np.ndarray:
    """For each truck, how many other vehicles or people it partly covers."""
    n = len(types)
    covers = np.zeros(n, dtype=int)
    trucks = [i for i in range(n) if types[i] == "truck"]
    for i in trucks:
        tx1, ty1, tx2, ty2 = xyxy[i]
        for j in range(n):
            if j == i or types[j] == "truck":
                continue
            x1, y1, x2, y2 = xyxy[j]
            iw, ih = max(0.0, min(tx2, x2) - max(tx1, x1)), max(0.0, min(ty2, y2) - max(ty1, y1))
            area = max(1.0, (x2 - x1) * (y2 - y1))
            if iw * ih / area >= HIDE_OVERLAP:
                covers[i] += 1
    return covers


class JunctionTracker:
    """Tracks vehicles and pedestrians and produces per-road statistics."""

    def __init__(self, roads: list[dict], crossings: list[dict]) -> None:
        self.set_zones(roads, crossings)
        self._history: dict[int, deque] = defaultdict(lambda: deque(maxlen=120))
        self._stopped_since: dict[int, float] = {}
        self._first_seen_in_road: dict[str, dict[int, float]] = defaultdict(dict)  # for arrival rates
        self._started: float | None = None

    def set_zones(self, roads: list[dict], crossings: list[dict]) -> None:
        self.roads = zones_from_config(roads)
        self.crossings = zones_from_config(crossings)

    def _arrivals_per_min(self, road_id: str, ids_inside, t: float) -> float:
        """How many new vehicles entered this road's zone per minute (last 60 s)."""
        seen = self._first_seen_in_road[road_id]
        for tid in ids_inside:
            seen.setdefault(int(tid), t)
        for tid in [k for k, v in seen.items() if t - v > 120]:
            del seen[tid]
        window = min(60.0, max(t - (self._started or t), 1.0))
        recent = sum(1 for v in seen.values() if t - v <= window)
        return round(recent * 60.0 / window, 1)

    def _update_motion(self, detections: sv.Detections, t: float) -> np.ndarray:
        """Record anchor positions and return a 'stopped' mask per detection."""
        stopped = np.zeros(len(detections), dtype=bool)
        if len(detections) == 0 or detections.tracker_id is None:
            return stopped
        points = detections.get_anchors_coordinates(ANCHOR)
        for i, (tid, (x, y)) in enumerate(zip(detections.tracker_id, points)):
            history = self._history[int(tid)]
            history.append((t, float(x), float(y)))
            while history and t - history[0][0] > TRACK_HISTORY_SECONDS:
                history.popleft()
            t0, x0, y0 = history[0]
            elapsed = t - t0
            if elapsed < 0.5:
                continue  # not enough history yet to judge speed
            speed = np.hypot(x - x0, y - y0) / elapsed
            if speed < STOPPED_SPEED_PX_S:
                stopped[i] = True
                self._stopped_since.setdefault(int(tid), t0)
            else:
                self._stopped_since.pop(int(tid), None)
        return stopped

    def _forget_old_tracks(self, active_ids: set[int], t: float) -> None:
        for tid in list(self._history):
            if tid not in active_ids and (not self._history[tid] or t - self._history[tid][-1][0] > 5):
                self._history.pop(tid, None)
                self._stopped_since.pop(tid, None)

    def update(self, detections: sv.Detections, width: int, height: int, t: float) -> tuple[sv.Detections, dict]:
        """Take one frame of tracked detections and return (detections, stats)."""
        if self._started is None:
            self._started = t
        if detections.tracker_id is None:
            detections.tracker_id = np.full(len(detections), -1, dtype=int)
        tracked = detections[detections.tracker_id >= 0]
        if "type" not in tracked.data:
            tracked.data["type"] = np.array([], dtype=object)
        stopped = self._update_motion(tracked, t)
        tracked.data["stopped"] = stopped
        active = set(int(i) for i in tracked.tracker_id) if tracked.tracker_id is not None else set()
        self._forget_old_tracks(active, t)

        types = tracked.data["type"]
        is_vehicle = np.isin(types, VEHICLE_TYPES) if len(tracked) else np.zeros(0, dtype=bool)
        is_person = (types == "person") if len(tracked) else np.zeros(0, dtype=bool)

        covers = hidden_behind_trucks(tracked.xyxy, types) if len(tracked) else np.zeros(0, dtype=int)
        roads_stats = []
        for road in self.roads:
            inside = road.trigger(tracked, width, height) & is_vehicle
            counts: dict[str, int] = {}
            for vtype in types[inside]:
                counts[vtype] = counts.get(vtype, 0) + 1
            queued = inside & stopped
            waits = [t - self._stopped_since[int(tid)]
                     for tid in tracked.tracker_id[queued] if int(tid) in self._stopped_since]
            ids_inside = tracked.tracker_id[inside] if tracked.tracker_id is not None else []
            roads_stats.append({
                "id": road.id,
                "name": road.name,
                "vehicles": counts,
                "total_vehicles": int(inside.sum()),
                "queued": int(queued.sum()),
                "longest_wait_s": round(max(waits), 1) if waits else 0.0,
                "queued_waits": [round(w, 1) for w in waits],
                "arrivals_per_min": self._arrivals_per_min(road.id, ids_inside, t),
                # trucks in this road, and vehicles or riders they partly hide
                "trucks": int(counts.get("truck", 0)),
                "partly_hidden": int(covers[inside].sum()) if len(covers) else 0,
            })

        crossing_stats = []
        for crossing in self.crossings:
            inside = crossing.trigger(tracked, width, height) & is_person
            crossing_stats.append({"id": crossing.id, "name": crossing.name, "people": int(inside.sum())})

        stats = {
            "roads": roads_stats,
            "crossings": crossing_stats,
            "total_vehicles": int(is_vehicle.sum()),
            "total_people_detected": int(is_person.sum()),
        }
        return tracked, stats
