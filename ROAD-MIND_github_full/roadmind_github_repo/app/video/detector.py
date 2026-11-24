"""YOLO vehicle and pedestrian detector (with ByteTrack tracking built in).

The detector maps whatever class names the model knows onto Roadmind's own
vehicle types. A pretrained COCO model knows car, bus, truck, motorcycle,
bicycle and person, but NOT Bangladeshi types such as CNG, rickshaw or leguna.
A model fine-tuned on a Bangladeshi dataset (placed at models/roadmind.pt)
adds those automatically, as long as its class names match the aliases below.
"""
from __future__ import annotations

import numpy as np
import supervision as sv
from ultralytics import YOLO

from app.config import DETECT_CONFIDENCE, DETECT_IMG_SIZE, ROOT

# Model class name (lower case) -> Roadmind type
ALIASES: dict[str, str] = {
    "person": "person", "pedestrian": "person", "people": "person",
    "bicycle": "bicycle", "cycle": "bicycle",
    "car": "car", "sedan": "car", "suv": "car", "microbus": "car", "taxi": "car",
    "motorcycle": "motorbike", "motorbike": "motorbike", "bike": "motorbike",
    "bus": "bus", "minibus": "bus", "minibus/bus": "bus",
    "truck": "truck", "pickup": "truck", "lorry": "truck",
    "van": "van", "covered van": "van",
    "cng": "cng", "auto rickshaw": "cng", "autorickshaw": "cng", "three wheelers (cng)": "cng",
    "rickshaw": "rickshaw", "cycle rickshaw": "rickshaw",
    "battery rickshaw": "battery_rickshaw", "easy bike": "battery_rickshaw", "easybike": "battery_rickshaw",
    "leguna": "leguna", "human hauler": "leguna",
}

VEHICLE_TYPES = ("bus", "leguna", "battery_rickshaw", "cng", "rickshaw", "car",
                 "van", "motorbike", "bicycle", "truck")
# Open vehicles whose riders YOLO also sees as "person" boxes
RIDDEN_TYPES = ("motorbike", "bicycle", "rickshaw", "battery_rickshaw")


BUS_MIN_CONFIDENCE = 0.5  # a bus adds ~40 people, so only count one when the AI is sure


def demote_unsure_buses(types: np.ndarray, confidence: np.ndarray | None) -> np.ndarray:
    """An unsure 'bus' (often a lorry seen from the front) is counted as a truck instead.

    One wrong bus would add ~40 people and swing the advice, so a bus needs a confident detection.
    """
    if confidence is None or not len(types):
        return types
    types = types.copy()
    types[(types == "bus") & (confidence < BUS_MIN_CONFIDENCE)] = "truck"
    return types


def mark_riders(xyxy: np.ndarray, types: np.ndarray) -> np.ndarray:
    """Relabel 'person' boxes that sit on a motorbike/bicycle/rickshaw as 'rider'.

    Riders are already counted through the vehicle's occupancy, so they must not
    also count as pedestrians waiting to cross.
    """
    types = types.copy()
    persons = np.where(types == "person")[0]
    ridden = np.where(np.isin(types, RIDDEN_TYPES))[0]
    for i in persons:
        px1, py1, px2, py2 = xyxy[i]
        cx, area = (px1 + px2) / 2, max((px2 - px1) * (py2 - py1), 1.0)
        for j in ridden:
            vx1, vy1, vx2, vy2 = xyxy[j]
            iw = max(0.0, min(px2, vx2) - max(px1, vx1))
            ih = max(0.0, min(py2, vy2) - max(py1, vy1))
            # most of the person's lower body overlaps the vehicle, and they are above it
            if vx1 <= cx <= vx2 and iw * ih / area >= 0.25 and py2 <= vy2 + 0.15 * (vy2 - vy1):
                types[i] = "rider"
                break
    return types


def _normalise(name: str) -> str:
    return name.lower().replace("_", " ").replace("-", " ").strip()


class Detector:
    """Wraps a YOLO model and returns supervision Detections with a 'type' field."""

    def __init__(self, model_path: str) -> None:
        path = ROOT / model_path
        # If official weights (e.g. yolo11n.pt) are missing, Ultralytics downloads them here
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model = YOLO(str(path))
        self.class_to_type: dict[int, str] = {}
        for class_id, name in self.model.names.items():
            roadmind_type = ALIASES.get(_normalise(name))
            if roadmind_type:
                self.class_to_type[int(class_id)] = roadmind_type
        self.keep_ids = np.array(sorted(self.class_to_type), dtype=int)

    @property
    def supported_types(self) -> list[str]:
        """Roadmind types this model can actually detect (shown honestly in the UI)."""
        return sorted(set(self.class_to_type.values()))

    def detect(self, frame: np.ndarray) -> sv.Detections:
        """Detect and track in one step (Ultralytics' built-in ByteTrack keeps IDs stable)."""
        # agnostic_nms: one box per object (no "car" AND "truck" on the same CNG = no double count)
        result = self.model.track(frame, imgsz=DETECT_IMG_SIZE, conf=DETECT_CONFIDENCE, agnostic_nms=True,
                                  tracker="bytetrack.yaml", persist=True, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(result)
        if detections.tracker_id is None:  # nothing tracked yet (or an empty frame)
            detections.tracker_id = np.full(len(detections), -1, dtype=int)
        if len(detections) == 0:
            detections.data["type"] = np.array([], dtype=object)
            return detections
        detections = detections[np.isin(detections.class_id, self.keep_ids)]
        types = np.array([self.class_to_type[int(c)] for c in detections.class_id], dtype=object)
        types = demote_unsure_buses(types, detections.confidence)
        detections.data["type"] = mark_riders(detections.xyxy, types)
        return detections
