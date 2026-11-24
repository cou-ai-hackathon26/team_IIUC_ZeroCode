"""Find the road zones automatically by watching where vehicles move.

How it works (no extra model needed):
1. Watch the first ~20 seconds of the video with the same YOLO + ByteTrack as the live view.
2. Each tracked vehicle gives a path. Its direction (angle) tells which approach it came from.
3. Paths are grouped by direction (at most 4 groups = 4 roads).
4. For each group, the zone is the area covered by the first part of the paths
   (the approach, before vehicles reach the middle of the junction).

This runs by itself when a camera has no road zones yet. Road names come from the junction file
(set once when the camera is installed); without them, roads are named by the side they come from.
"""
from __future__ import annotations

import math
import time

import cv2
import numpy as np

from app.config import MODEL_PATH
from app.video.detector import Detector
from app.video.source import resize_for_processing, resolve_source

ARROWS = ["→", "↘", "↓", "↙", "←", "↖", "↑", "↗"]  # heading of traffic, 45° steps (image y points down)


def _heading_arrow(angle: float) -> str:
    return ARROWS[int(round(angle / (math.pi / 4))) % 8]


SIDES = ("top", "bottom", "left", "right")


def side_from_heading(angle: float) -> str:
    """Which side of the camera view the traffic comes FROM (image y points down)."""
    dx, dy = math.cos(angle), math.sin(angle)
    if abs(dy) >= abs(dx):
        return "top" if dy > 0 else "bottom"
    return "left" if dx > 0 else "right"


def _angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % (2 * math.pi)
    return min(d, 2 * math.pi - d)


def zones_from_tracks(tracks: dict[int, list[tuple]], width: int, height: int,
                      max_roads: int = 4, road_names: dict | None = None) -> list[dict]:
    """Turn vehicle paths into road zones (normalised polygons).

    Each path point is (x, y) or (x, y, box_width, box_height): x, y is the bottom-centre of the vehicle.
    """
    diag = math.hypot(width, height)
    default_size = 0.06 * diag
    moves = []
    for pts in tracks.values():
        if len(pts) < 6:
            continue
        p = np.array([(q[0], q[1], q[2] if len(q) > 2 else default_size, q[3] if len(q) > 3 else default_size)
                      for q in pts], dtype=float)
        start, end = p[:3, :2].mean(axis=0), p[-3:, :2].mean(axis=0)
        d = end - start
        if math.hypot(*d) < 0.04 * diag:  # parked or barely moving
            continue
        moves.append((math.atan2(d[1], d[0]), p))
    if len(moves) < 3:
        return []

    # Direction histogram (12 bins of 30°), lightly smoothed around the circle.
    bins = 12
    hist = np.zeros(bins)
    for ang, _ in moves:
        hist[int(((ang + math.pi) / (2 * math.pi)) * bins) % bins] += 1
    smooth = hist + 0.5 * (np.roll(hist, 1) + np.roll(hist, -1))
    min_count = max(2, 0.12 * len(moves))
    peaks: list[float] = []
    work = smooth.copy()
    while len(peaks) < max_roads:
        i = int(work.argmax())
        if work[i] < min_count:
            break
        peaks.append(-math.pi + (i + 0.5) * 2 * math.pi / bins)
        for k in range(-2, 3):  # suppress ±60° around this direction
            work[(i + k) % bins] = 0

    groups: list[list[np.ndarray]] = [[] for _ in peaks]
    for ang, p in moves:
        best = min(range(len(peaks)), key=lambda j: _angle_diff(ang, peaks[j]))
        if _angle_diff(ang, peaks[best]) <= math.radians(60):
            groups[best].append(p)

    roads = []
    for peak, paths in zip(peaks, groups):
        if len(paths) < 2:
            continue
        # approach part = first 60% of each path, widened by half a vehicle so the zone covers the lane
        part = np.vstack([p[: max(3, int(len(p) * 0.6))] for p in paths])
        x, y, bw, bh = part[:, 0], part[:, 1], part[:, 2] / 2, part[:, 3] / 4
        pts = np.concatenate([np.stack([x - bw, y - bh], 1), np.stack([x + bw, y - bh], 1),
                              np.stack([x - bw, y + bh], 1), np.stack([x + bw, y + bh], 1)]).astype(np.float32)
        hull = cv2.convexHull(pts).reshape(-1, 2)
        approx = cv2.approxPolyDP(hull.astype(np.float32).reshape(-1, 1, 2), 0.01 * diag, True).reshape(-1, 2)
        if len(approx) < 3:
            approx = hull
        poly = [[round(float(np.clip(x / width, 0, 1)), 4), round(float(np.clip(y / height, 0, 1)), 4)]
                for x, y in approx]
        roads.append({"polygon": poly, "heading": peak, "vehicles": len(paths)})

    roads.sort(key=lambda r: -r["vehicles"])
    # Names: the junction file can hold the real road names by the side of the camera view they
    # come from (set once when the camera is installed), e.g. {"left": "Agrabad Road"}.
    names = {k: str(v) for k, v in (road_names or {}).items() if k in SIDES and v}
    result, used = [], set()
    for i, r in enumerate(roads):
        side = side_from_heading(r["heading"])
        name = names.get(side) or f"From the {side}"
        if name in used:
            name = f"{name} {i + 1}"
        used.add(name)
        result.append({"id": f"R{i + 1}", "name": name, "side": side,
                       "polygon": r["polygon"], "vehicles_seen": r["vehicles"]})
    return result


def detect_zones(source: str, seconds: float = 20, max_frames: int = 240, time_limit: float = 60,
                 road_names: dict | None = None) -> dict:
    """Watch the start of a video source and return suggested road zones."""
    cap = cv2.VideoCapture(resolve_source(source))
    if not cap.isOpened():
        return {"roads": [], "error": "Cannot open the video source"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    fps = fps if 1 <= fps <= 120 else 25
    step = max(1, int(round(fps / 8)))  # about 8 analysed frames per video second
    detector = Detector(MODEL_PATH)
    tracks: dict[int, list[tuple[float, float]]] = {}
    w = h = 0
    analysed, index, started = 0, 0, time.time()
    try:
        while analysed < max_frames and index < seconds * fps and time.time() - started < time_limit:
            ok, frame = cap.read()
            if not ok:
                break
            index += 1
            if index % step:
                continue
            frame = resize_for_processing(frame)
            h, w = frame.shape[:2]
            det = detector.detect(frame)
            analysed += 1
            types = det.data.get("type", [])
            for k in range(len(det)):
                tid = int(det.tracker_id[k]) if det.tracker_id is not None else -1
                if tid < 0 or (len(types) and types[k] in ("person", "rider")):
                    continue
                x1, y1, x2, y2 = det.xyxy[k]
                tracks.setdefault(tid, []).append(((x1 + x2) / 2, y2, x2 - x1, y2 - y1))  # bottom-centre = on the road
    finally:
        cap.release()
    if not w:
        return {"roads": [], "error": "Could not read frames from the video source"}
    roads = zones_from_tracks(tracks, w, h, road_names=road_names)
    note = None if roads else "Not enough moving vehicles were seen. Use a clip with moving traffic, or draw the zones by hand."
    return {"roads": roads, "vehicles_tracked": len(tracks), "frames": analysed, "error": note}
