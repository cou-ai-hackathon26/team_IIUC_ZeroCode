"""Measure counting accuracy against hand-counted ground truth.

Ground-truth CSV (one row per road, vehicle type and moment you counted by hand):

    second,road_id,type,count
    10,R1,bus,2
    10,R1,car,5
    10,R2,cng,3

Usage:
    python scripts/evaluate_counts.py --junction demo --gt data/ground_truth/demo.csv
    python scripts/evaluate_counts.py --junction demo --clip data/clips/other.mp4 --gt data/ground_truth/other.csv

Prints a Markdown table (paste it into the README) and saves it to results/.
Report weak results honestly — they show where fine-tuning is needed.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from offline import ROOT, iterate_clip


def load_gt(path: str) -> dict[float, dict[tuple[str, str], int]]:
    truth: dict[float, dict[tuple[str, str], int]] = defaultdict(dict)
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            truth[float(row["second"])][(row["road_id"].strip(), row["type"].strip())] = int(row["count"])
    return truth


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--junction", required=True)
    ap.add_argument("--gt", required=True, help="ground-truth CSV")
    ap.add_argument("--clip", help="video file (defaults to the junction's source)")
    args = ap.parse_args()

    truth = load_gt(args.gt)
    moments = sorted(truth)
    predicted: dict[float, dict[tuple[str, str], int]] = {}
    pending = list(moments)
    for seconds, stats in iterate_clip(args.junction, args.clip):
        while pending and seconds >= pending[0]:
            snap = {}
            for road in stats["roads"]:
                for vtype, n in road["vehicles"].items():
                    snap[(road["id"], vtype)] = n
            predicted[pending.pop(0)] = snap
        if not pending:
            break

    per_type_err, per_type_total = defaultdict(int), defaultdict(int)
    per_road_abs, per_road_n = defaultdict(int), defaultdict(int)
    for moment in moments:
        gt, pred = truth[moment], predicted.get(moment, {})
        keys = set(gt) | {k for k in pred if k[0] in {r for r, _ in gt}}
        road_gt, road_pred = defaultdict(int), defaultdict(int)
        for road, vtype in keys:
            g, p = gt.get((road, vtype), 0), pred.get((road, vtype), 0)
            per_type_err[vtype] += abs(g - p)
            per_type_total[vtype] += max(g, p)
            road_gt[road] += g
            road_pred[road] += p
        for road in road_gt:
            per_road_abs[road] += abs(road_gt[road] - road_pred[road])
            per_road_n[road] += 1

    lines = [f"### Counting accuracy — junction `{args.junction}`, {len(moments)} hand-counted moments", "",
             "| Vehicle type | Accuracy | Total counted (max of truth/AI) |", "|---|---|---|"]
    for vtype in sorted(per_type_total):
        acc = 1 - per_type_err[vtype] / per_type_total[vtype] if per_type_total[vtype] else 1.0
        lines.append(f"| {vtype} | {acc:.0%} | {per_type_total[vtype]} |")
    lines += ["", "| Road | Mean absolute counting error (vehicles) |", "|---|---|"]
    for road in sorted(per_road_n):
        lines.append(f"| {road} | {per_road_abs[road] / per_road_n[road]:.2f} |")
    report = "\n".join(lines)
    print(report)
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / f"eval_{args.junction}.md").write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
