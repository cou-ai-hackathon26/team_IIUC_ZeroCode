"""Process a recorded junction clip and save per-minute counts for rhythm mode.

Run real detection over a clip recorded at a known date and time; every minute
of video becomes one history point (average people waiting at the junction).
Record clips at different times (Friday noon, school release, evening) so the
forecast learns the junction's local rhythm.

Usage:
    python scripts/record_counts.py --junction demo --clip data/clips/gec_fri_1230.mp4 --start "2026-11-27 12:30"
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta

from offline import iterate_clip

from app import db
from app.core.rhythm import TZ, day_kind


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--junction", required=True)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--start", required=True, help='when the clip was recorded, e.g. "2026-11-27 12:30" (Bangladesh time)')
    ap.add_argument("--detect-every", type=int, default=3, help="run detection on every Nth frame (default 3)")
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    minute_people, minute_vehicles, minute_roads = [], [], {}
    current_minute, saved = 0, 0

    def flush(minute_index: int) -> None:
        nonlocal saved
        if not minute_people:
            return
        when = start + timedelta(minutes=minute_index)
        per_road = {rid: round(sum(v) / len(v), 1) for rid, v in minute_roads.items()}
        db.add_counts(args.junction, when.isoformat(), day_kind(when), when.hour * 60 + when.minute,
                      round(sum(minute_people) / len(minute_people), 1),
                      round(sum(minute_vehicles) / len(minute_vehicles), 1), per_road, source="recorded")
        saved += 1
        print(f"{when:%a %H:%M}  people≈{per_road}")

    for seconds, stats in iterate_clip(args.junction, args.clip, args.detect_every):
        minute = int(seconds // 60)
        if minute != current_minute:
            flush(current_minute)
            minute_people.clear(); minute_vehicles.clear(); minute_roads.clear()
            current_minute = minute
        minute_people.append(sum(r["people"] for r in stats["roads"]))
        minute_vehicles.append(sum(r["total_vehicles"] for r in stats["roads"]))
        for r in stats["roads"]:
            minute_roads.setdefault(r["id"], []).append(r["people"])
    flush(current_minute)
    print(f"Saved {saved} minute(s) of history for '{args.junction}'.")


if __name__ == "__main__":
    main()
