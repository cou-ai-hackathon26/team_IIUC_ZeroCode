"""Shared helper for the offline scripts: run real detection over a clip, frame by frame.

Time comes from the video itself (frame number / fps), so results do not depend
on how fast the computer is.
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import MODEL_PATH  # noqa: E402
from app.core.people import add_people, merged_occupancy  # noqa: E402
from app.junctions import load_junction  # noqa: E402
from app.video.detector import Detector  # noqa: E402
from app.video.source import resize_for_processing, resolve_source  # noqa: E402
from app.video.tracker import JunctionTracker  # noqa: E402


def iterate_clip(junction_id: str, clip: str | None = None, detect_every: int = 1):
    """Yield (video_seconds, per-road stats with people) for every processed frame."""
    junction = load_junction(junction_id)
    cap = cv2.VideoCapture(resolve_source(clip or junction["source"]))
    if not cap.isOpened():
        raise SystemExit(f"Cannot open clip: {clip or junction['source']}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    detector = Detector(MODEL_PATH)
    tracker = JunctionTracker(junction["roads"], junction["crossings"])
    occupancy = merged_occupancy(junction.get("occupancy"))
    index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        index += 1
        if index % detect_every:
            continue
        frame = resize_for_processing(frame)
        h, w = frame.shape[:2]
        seconds = index / fps
        _, stats = tracker.update(detector.detect(frame), w, h, seconds)
        stats["roads"] = add_people(stats["roads"], occupancy)
        yield seconds, stats
    cap.release()
