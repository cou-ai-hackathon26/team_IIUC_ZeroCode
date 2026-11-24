"""Video input for Roadmind.

A VideoSource reads frames in a background thread and always keeps only the
latest frame, so slow processing never builds up a delay. It accepts:

- a video file path (looped forever, played at its real speed)
- a webcam index such as "0"
- a phone IP-camera / MJPEG URL (http://...)
- an RTSP URL from a CCTV camera (rtsp://...)
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from app.config import PROCESS_MAX_WIDTH, ROOT
from app.config import SLOW_MODE, SLOW_STRIDE


def resolve_source(source: str) -> str | int:
    """Turn the junction's "source" text into something OpenCV can open."""
    source = str(source).strip()
    if source.isdigit():
        return int(source)  # webcam index
    if "://" in source:
        return source  # http / rtsp stream
    path = Path(source)
    if not path.is_absolute():
        path = ROOT / path
    return str(path)


def is_file_source(source: str | int) -> bool:
    return isinstance(source, str) and "://" not in source


def resize_for_processing(frame: np.ndarray) -> np.ndarray:
    """Shrink wide frames to PROCESS_MAX_WIDTH, keeping the aspect ratio."""
    h, w = frame.shape[:2]
    if w <= PROCESS_MAX_WIDTH:
        return frame
    scale = PROCESS_MAX_WIDTH / w
    return cv2.resize(frame, (PROCESS_MAX_WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)


def open_capture(source: str | int) -> cv2.VideoCapture:
    """Open a video source with the fastest settings for its kind."""
    if isinstance(source, int) and sys.platform == "win32":
        cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)  # opens webcams much faster on Windows
    else:
        cap = cv2.VideoCapture(source)
    if not is_file_source(source):
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # live: keep only the newest frame
    return cap


def grab_first_frame(source: str) -> np.ndarray | None:
    """Read one frame (used by the calibration page to draw zones on)."""
    cap = open_capture(resolve_source(source))
    try:
        ok, frame = cap.read()
        return resize_for_processing(frame) if ok else None
    finally:
        cap.release()


class VideoSource:
    """Threaded reader that always holds the most recent frame."""

    def __init__(self, source: str) -> None:
        self.source_text = source
        self.source = resolve_source(source)
        self._is_file = is_file_source(self.source)
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_id = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self.error: str | None = None
        self._consumed_id = 0      # last frame the AI finished (slow mode waits for it)
        self.wait_for_ai = SLOW_MODE   # the pipeline turns this off once the roads are known
        self._video_time = 0.0     # seconds of the video played so far (files)

    def start(self) -> "VideoSource":
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._running = False

    def consumed(self, frame_id: int) -> None:
        """The AI has finished this frame (used by slow mode)."""
        self._consumed_id = max(self._consumed_id, frame_id)

    @property
    def is_file(self) -> bool:
        return self._is_file

    @property
    def video_time(self) -> float:
        return self._video_time

    def read(self) -> tuple[np.ndarray | None, int]:
        """Return (latest frame, frame number). Frame is None until the first one arrives."""
        with self._lock:
            return self._frame, self._frame_id

    def _loop(self) -> None:
        while self._running:
            cap = open_capture(self.source)
            if not cap.isOpened():
                if self._is_file and not Path(str(self.source)).exists():
                    self.error = "No video yet. Press ⬆ Upload video (or 📷 Camera) at the top to start."
                else:
                    self.error = f"Cannot open video source: {self.source_text}"
                time.sleep(2)
                continue
            self.error = None
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            frame_gap = 1.0 / fps if self._is_file and 1 <= fps <= 120 else 0.0
            next_time = time.perf_counter()
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    break  # end of file (loop again) or stream dropped (reconnect)
                frame = resize_for_processing(frame)
                with self._lock:
                    self._frame = frame
                    self._frame_id += 1
                    current = self._frame_id
                self._video_time += 1.0 / fps if fps else 0.04
                if self.wait_for_ai and self._is_file:
                    # only while the roads are being found: wait until the AI has looked at this
                    # frame (it needs to see the cars move), then skip ahead a little
                    waited = time.perf_counter()
                    while self._running and self._consumed_id < current and time.perf_counter() - waited < 15:
                        time.sleep(0.01)
                    for _ in range(SLOW_STRIDE - 1):
                        if not cap.grab():
                            break
                        self._video_time += 1.0 / fps if fps else 0.04
                    continue
                if frame_gap:  # play files at their real speed
                    next_time += frame_gap
                    delay = next_time - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                    else:
                        next_time = time.perf_counter()
            cap.release()
            if not self._is_file:
                time.sleep(1)  # brief pause before reconnecting a live stream
