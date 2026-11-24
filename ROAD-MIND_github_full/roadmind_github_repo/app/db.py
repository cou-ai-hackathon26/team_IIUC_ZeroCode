"""SQLite storage: the decision log and the per-minute counts history.

Thumbnails saved with a decision are tiny and heavily blurred, so no faces or
number plates can be recognised. Raw frames are never stored.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import cv2
import numpy as np

from app.config import DATA_DIR

DB_PATH = DATA_DIR / "roadmind.db"
THUMBS_DIR = DATA_DIR / "thumbs"
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                junction TEXT NOT NULL,
                created_at REAL NOT NULL,
                mode TEXT NOT NULL,
                advice TEXT NOT NULL,
                explanation TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                chosen_seconds INTEGER,
                reason TEXT,
                decided_at REAL,
                thumb TEXT
            );
            CREATE TABLE IF NOT EXISTS counts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                junction TEXT NOT NULL,
                ts TEXT NOT NULL,
                day_kind TEXT NOT NULL,
                minute INTEGER NOT NULL,
                people REAL NOT NULL,
                vehicles REAL NOT NULL,
                per_road TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'live'
            );
        """)
    return _conn


def save_thumbnail(frame: np.ndarray, name: str) -> str:
    """Store a tiny, strongly blurred thumbnail (privacy: nothing identifiable)."""
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    small = cv2.resize(frame, (240, int(240 * frame.shape[0] / frame.shape[1])), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (15, 15), 0)
    path = THUMBS_DIR / f"{name}.jpg"
    cv2.imwrite(str(path), small, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return path.name


def add_decision(junction: str, advice: dict, explanation: dict, thumb: str | None) -> int:
    status = {"keep_fixed": "low_confidence", "emergency": "emergency"}.get(advice.get("mode"), "pending")
    with _lock:
        db = _db()
        # an older pending advice that was never answered is marked as superseded
        db.execute("UPDATE decisions SET status='no_response' WHERE junction=? AND status='pending'", (junction,))
        cur = db.execute(
            "INSERT INTO decisions (junction, created_at, mode, advice, explanation, status, thumb) VALUES (?,?,?,?,?,?,?)",
            (junction, time.time(), advice.get("mode", ""), json.dumps(advice), json.dumps(explanation, ensure_ascii=False), status, thumb))
        db.commit()
        return int(cur.lastrowid)


def update_explanation(decision_id: int, explanation: dict) -> None:
    with _lock:
        db = _db()
        db.execute("UPDATE decisions SET explanation=? WHERE id=?", (json.dumps(explanation, ensure_ascii=False), decision_id))
        db.commit()


def decide(decision_id: int, action: str, seconds: int | None, reason: str | None) -> dict | None:
    status = {"accept": "accepted", "override": "overridden"}[action]
    with _lock:
        db = _db()
        row = db.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
        if row is None:
            return None
        if row["status"] in ("accepted", "overridden"):
            return {"already_decided": True, "status": row["status"]}
        db.execute("UPDATE decisions SET status=?, chosen_seconds=?, reason=?, decided_at=? WHERE id=?",
                   (status, seconds, (reason or "")[:80] or None, time.time(), decision_id))
        db.commit()
    return get_decision(decision_id)


def _row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["advice"] = json.loads(d["advice"])
    d["explanation"] = json.loads(d["explanation"])
    return d


def get_decision(decision_id: int) -> dict | None:
    with _lock:
        row = _db().execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
    return _row(row) if row else None


def recent_decisions(junction: str, limit: int = 20) -> list[dict]:
    with _lock:
        rows = _db().execute("SELECT * FROM decisions WHERE junction=? ORDER BY id DESC LIMIT ?",
                             (junction, limit)).fetchall()
    return [_row(r) for r in rows]


def add_counts(junction: str, ts: str, day_kind: str, minute: int, people: float, vehicles: float,
               per_road: dict, source: str = "live") -> None:
    with _lock:
        db = _db()
        db.execute("INSERT INTO counts (junction, ts, day_kind, minute, people, vehicles, per_road, source) VALUES (?,?,?,?,?,?,?,?)",
                   (junction, ts, day_kind, minute, people, vehicles, json.dumps(per_road), source))
        db.commit()


def counts_history(junction: str, limit: int = 5000) -> list[dict]:
    with _lock:
        rows = _db().execute("SELECT ts, day_kind, minute, people FROM counts WHERE junction=? ORDER BY id DESC LIMIT ?",
                             (junction, limit)).fetchall()
    return [dict(r) for r in rows]


def thumb_path(name: str) -> Path | None:
    path = (THUMBS_DIR / name).resolve()
    if path.parent != THUMBS_DIR.resolve() or not path.exists():
        return None
    return path
