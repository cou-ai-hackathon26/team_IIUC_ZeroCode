"""Drawing overlays on the video: road zones, crossings, boxes and labels."""
from __future__ import annotations

import cv2
import numpy as np
import supervision as sv

from app.video.tracker import Zone

# BGR colours per vehicle type
TYPE_COLOURS: dict[str, tuple[int, int, int]] = {
    "bus": (11, 158, 245), "truck": (60, 130, 200), "car": (250, 165, 96),
    "cng": (94, 197, 34), "rickshaw": (249, 121, 232), "battery_rickshaw": (247, 85, 168),
    "leguna": (153, 246, 228), "van": (184, 163, 148), "motorbike": (245, 241, 241),
    "bicycle": (210, 210, 210), "person": (138, 230, 253), "rider": (200, 200, 160), "other": (180, 180, 180),
}
ROAD_COLOURS = [(248, 189, 56), (153, 211, 52), (247, 85, 168), (60, 160, 250), (167, 139, 250), (94, 234, 212)]
CROSSING_COLOUR = (138, 230, 253)
TYPE_LABELS = {"battery_rickshaw": "E-rickshaw", "cng": "CNG", "motorbike": "Motorbike"}
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _label(img: np.ndarray, text: str, x: int, y: int, bg: tuple[int, int, int],
           fg: tuple[int, int, int] = (20, 16, 4), scale: float = 0.42) -> None:
    (tw, th), _ = cv2.getTextSize(text, FONT, scale, 1)
    x = int(max(0, min(x, img.shape[1] - tw - 8)))
    y = int(max(th + 6, y))
    cv2.rectangle(img, (x, y - th - 6), (x + tw + 8, y), bg, -1)
    cv2.putText(img, text, (x + 4, y - 4), FONT, scale, fg, 1, cv2.LINE_AA)


def draw_zones(img: np.ndarray, roads: list[Zone], crossings: list[Zone], stats: dict) -> None:
    h, w = img.shape[:2]
    overlay = img.copy()
    road_stats = {r["id"]: r for r in stats.get("roads", [])}
    for i, road in enumerate(roads):
        if len(road.polygon) < 3:
            continue
        colour = ROAD_COLOURS[i % len(ROAD_COLOURS)]
        poly = road.pixel_polygon(w, h)
        cv2.fillPoly(overlay, [poly], colour)
    for crossing in crossings:
        if len(crossing.polygon) >= 3:
            cv2.fillPoly(overlay, [crossing.pixel_polygon(w, h)], CROSSING_COLOUR)
    cv2.addWeighted(overlay, 0.14, img, 0.86, 0, dst=img)

    for i, road in enumerate(roads):
        if len(road.polygon) < 3:
            continue
        colour = ROAD_COLOURS[i % len(ROAD_COLOURS)]
        poly = road.pixel_polygon(w, h)
        cv2.polylines(img, [poly], True, colour, 2, cv2.LINE_AA)
        s = road_stats.get(road.id, {})
        text = f"{road.name}: {s.get('total_vehicles', 0)} veh"
        if "people" in s:
            text += f" / about {s['people']:g} people"
        cx, cy = poly.mean(axis=0)
        _label(img, text, int(cx) - 70, int(cy), colour, scale=0.5)
    cross_stats = {c["id"]: c for c in stats.get("crossings", [])}
    for crossing in crossings:
        if len(crossing.polygon) < 3:
            continue
        poly = crossing.pixel_polygon(w, h)
        cv2.polylines(img, [poly], True, CROSSING_COLOUR, 1, cv2.LINE_AA)
        n = cross_stats.get(crossing.id, {}).get("people", 0)
        cx, cy = poly.mean(axis=0)
        _label(img, f"{crossing.name}: {n} waiting", int(cx) - 50, int(cy), CROSSING_COLOUR)


def draw_detections(img: np.ndarray, detections: sv.Detections, occupancy: dict | None = None) -> None:
    if len(detections) == 0:
        return
    types = detections.data.get("type", [])
    stopped = detections.data.get("stopped", np.zeros(len(detections), dtype=bool))
    ids = detections.tracker_id if detections.tracker_id is not None else [None] * len(detections)
    confs = detections.confidence if detections.confidence is not None else [None] * len(detections)
    for (x1, y1, x2, y2), vtype, tid, conf, is_stopped in zip(detections.xyxy, types, ids, confs, stopped):
        colour = TYPE_COLOURS.get(vtype, TYPE_COLOURS["other"])
        p1, p2 = (int(x1), int(y1)), (int(x2), int(y2))
        cv2.rectangle(img, p1, p2, colour, 2, cv2.LINE_AA)
        name = TYPE_LABELS.get(vtype, str(vtype).capitalize())
        text = name + (f" {conf:.2f}" if conf is not None else "") + (f" #{tid}" if tid is not None else "")
        if x2 - x1 > 28:
            _label(img, text, p1[0], p1[1], colour)
        # "people bubble": estimated people in this vehicle (an assumption, editable)
        if occupancy and vtype not in ("person", "rider") and x2 - x1 > 18:
            ppl = occupancy.get(vtype, occupancy.get("other", 1.5))
            bubble = f"{ppl:g}"
            (tw, th), _ = cv2.getTextSize(bubble, FONT, 0.4, 1)
            bx, by = int((x1 + x2) / 2 - tw / 2 - 5), int(y1) + 4
            cv2.rectangle(img, (bx, by), (bx + tw + 10, by + th + 8), (40, 24, 12), -1)
            cv2.putText(img, bubble, (bx + 5, by + th + 3), FONT, 0.4, (209, 250, 229), 1, cv2.LINE_AA)
        # small dot at the anchor: red = stopped (queued), green = moving
        cv2.circle(img, (int((x1 + x2) / 2), int(y2)), 3, (68, 68, 239) if is_stopped else (94, 197, 34), -1)


def annotate(frame: np.ndarray, detections: sv.Detections, roads: list[Zone],
             crossings: list[Zone], stats: dict, occupancy: dict | None = None) -> np.ndarray:
    img = frame.copy()
    draw_zones(img, roads, crossings, stats)
    draw_detections(img, detections, occupancy)
    return img
