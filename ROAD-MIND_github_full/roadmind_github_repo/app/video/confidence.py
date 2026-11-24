"""Confidence check: should we trust the camera right now?

Simple, explainable image checks, combined into a score from 0 to 1:
- Dark:   average brightness is very low (night, no street lights)
- Blur / rain: very little sharp detail (rain on the lens, fog, out of focus)
- View blocked: almost no edges or one flat colour (something covers the camera),
  or detections suddenly drop to zero when there were many a moment ago
- Low detection confidence: the detector itself is unsure

Level: High (>= 0.75), Medium (>= 0.5), Low (< 0.5). On Low the advisor keeps the
fixed timer instead of guessing. The score is smoothed so it does not flicker,
but still reacts within about one to two seconds.
"""
from __future__ import annotations

from collections import deque

import cv2
import numpy as np

DARK_BRIGHTNESS = 55          # mean grey level (0-255)
BLUR_SHARPNESS = 40           # variance of the Laplacian
BLOCKED_EDGE_DENSITY = 0.012  # fraction of edge pixels
BLOCKED_STD = 14              # grey-level standard deviation
LOW_DET_CONFIDENCE = 0.40

PENALTY = {"Dark": 0.35, "Blur / rain": 0.30, "View blocked": 0.65, "Low detection confidence": 0.25}


def image_measures(frame: np.ndarray) -> dict:
    small = cv2.resize(frame, (320, int(320 * frame.shape[0] / frame.shape[1])))
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(grey, 60, 160)
    return {
        "brightness": float(grey.mean()),
        "sharpness": float(cv2.Laplacian(grey, cv2.CV_64F).var()),
        "edge_density": float((edges > 0).mean()),
        "std": float(grey.std()),
    }


class ConfidenceChecker:
    def __init__(self, smoothing: float = 0.5) -> None:
        self.smoothing = smoothing
        self.score = 1.0
        self.recent_counts: deque[int] = deque(maxlen=30)
        self.last: dict = {"level": "High", "score": 1.0, "reasons": [], "measures": {}}

    def update(self, frame: np.ndarray, detection_count: int, mean_det_conf: float | None) -> dict:
        m = image_measures(frame)
        reasons = []
        if m["brightness"] < DARK_BRIGHTNESS:
            reasons.append("Dark")
        if m["sharpness"] < BLUR_SHARPNESS:
            reasons.append("Blur / rain")
        earlier = list(self.recent_counts)
        sudden_drop = len(earlier) >= 10 and np.mean(earlier) >= 4 and detection_count == 0
        if (m["edge_density"] < BLOCKED_EDGE_DENSITY and m["std"] < BLOCKED_STD) or sudden_drop:
            reasons.append("View blocked")
        if mean_det_conf is not None and detection_count >= 3 and mean_det_conf < LOW_DET_CONFIDENCE:
            reasons.append("Low detection confidence")
        self.recent_counts.append(detection_count)

        raw = max(0.0, 1.0 - sum(PENALTY[r] for r in reasons))
        self.score = self.smoothing * self.score + (1 - self.smoothing) * raw
        level = "High" if self.score >= 0.75 else "Medium" if self.score >= 0.5 else "Low"
        self.last = {"level": level, "score": round(self.score, 2), "reasons": reasons,
                     "measures": {k: round(v, 3) for k, v in m.items()}}
        return self.last
