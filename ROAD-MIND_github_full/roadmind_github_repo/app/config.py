"""Central settings for Roadmind.

Values come from the .env file where it makes sense; everything else has a
sensible default here so the app runs out of the box.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# --- Paths -----------------------------------------------------------------
JUNCTIONS_DIR = ROOT / "junctions"
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# --- Model and video -------------------------------------------------------
MODEL_PATH = os.getenv("ROADMIND_MODEL", "models/yolo11n.pt")
DEFAULT_JUNCTION = os.getenv("ROADMIND_DEFAULT_JUNCTION", "demo")
DETECT_EVERY = max(1, int(os.getenv("ROADMIND_DETECT_EVERY", "1")))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

PROCESS_MAX_WIDTH = 960   # frames are resized to this width before processing
# YOLO input size: 640 is fast; 960 finds small, far-away vehicles better but is ~2x slower.
DETECT_IMG_SIZE = int(os.getenv("ROADMIND_IMG_SIZE", "640"))
# Minimum detection confidence kept: lower finds more (and more mistakes), higher misses more.
DETECT_CONFIDENCE = float(os.getenv("ROADMIND_CONFIDENCE", "0.30"))
JPEG_QUALITY = 80         # quality of the annotated video stream (lower in slow mode, below)
DISPLAY_MAX_FPS = 20      # the dashboard video is drawn at most this often (lower in slow mode, below)

# --- Tracking --------------------------------------------------------------
# A vehicle counts as "stopped" (queued) when its anchor point moves slower
# than this many pixels per second (on the resized frame).
STOPPED_SPEED_PX_S = 12.0
TRACK_HISTORY_SECONDS = 2.0

# --- People-first estimate (ASSUMPTIONS, editable by the officer) ----------
DEFAULT_OCCUPANCY: dict[str, float] = {
    "bus": 40,
    "leguna": 12,
    "battery_rickshaw": 4,
    "cng": 3,
    "rickshaw": 2,
    "car": 1.5,
    "van": 1.5,
    "motorbike": 1.3,
    "bicycle": 1,
    "truck": 1.2,
    "other": 1.5,
}

# --- Signal timing (used by the advisor in a later step) -------------------
CYCLE_SECONDS = 120
MIN_GREEN = 10
MAX_GREEN = 60
MAX_WAIT_SECONDS = 120

# Slow servers (for example Render's free plan): play video files only as fast as the AI can look at
# them, so vehicles can still be followed frame to frame. The video looks slower, but the counts,
# the automatic road finding and the advice keep working. Leave off on a laptop.
SLOW_MODE = os.getenv("ROADMIND_SLOW_MODE", "0").strip().lower() in ("1", "true", "yes", "on")
SLOW_STRIDE = max(1, int(os.getenv("ROADMIND_SLOW_STRIDE", "6")))  # AI looks at every Nth frame

# On a small server (slow mode) the stream is made lighter so the video keeps moving smoothly:
# fewer pictures per second, a smaller picture and a little more JPEG compression.
if SLOW_MODE:
    DISPLAY_MAX_FPS = int(os.getenv("ROADMIND_DISPLAY_FPS", "12"))
    JPEG_QUALITY = int(os.getenv("ROADMIND_JPEG_QUALITY", "70"))
STREAM_MAX_WIDTH = int(os.getenv("ROADMIND_STREAM_WIDTH", "854" if SLOW_MODE else "0"))  # 0 = no limit
