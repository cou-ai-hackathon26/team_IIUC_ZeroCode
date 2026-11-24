"""Make detection 2-3x faster on a normal laptop CPU (Intel/AMD) with OpenVINO.

Usage (once, needs internet):
    pip install openvino
    python scripts/speed_up.py                 # fast:  yolo11n  (default)
    python scripts/speed_up.py --model yolo11s # more accurate, about as fast as plain yolo11n

Then put the line it prints into .env (ROADMIND_MODEL=...) and restart the app.
The exported model gives the same detections; it only runs faster.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="yolo11n", choices=["yolo11n", "yolo11s", "yolo11m"],
                        help="n = fastest, s = more accurate, m = most accurate (slow on CPU)")
    parser.add_argument("--imgsz", type=int, default=640, help="must match ROADMIND_IMG_SIZE")
    args = parser.parse_args()

    try:
        import openvino  # noqa: F401
    except ImportError:
        sys.exit("OpenVINO is not installed. Run:  pip install openvino   then run this script again.")
    from ultralytics import YOLO

    models = ROOT / "models"
    models.mkdir(exist_ok=True)
    weights = models / f"{args.model}.pt"
    print(f"Loading {weights.name} (downloads the first time)...")
    model = YOLO(str(weights))
    out = Path(model.export(format="openvino", imgsz=args.imgsz, half=False, verbose=False))
    target = models / f"{args.model}_openvino_model"
    if out.resolve() != target.resolve():
        shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(out), str(target))

    # quick speed check on a blank frame
    import numpy as np
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    for path in (weights, target):
        m = YOLO(str(path), task="detect")
        m.predict(frame, imgsz=args.imgsz, verbose=False)
        t = time.perf_counter()
        for _ in range(10):
            m.predict(frame, imgsz=args.imgsz, verbose=False)
        print(f"  {path.name:28s} {10 / (time.perf_counter() - t):5.1f} frames per second")

    print("\nDone. Add this line to your .env file, then restart the app:")
    print(f"ROADMIND_MODEL=models/{target.name}")
    if args.imgsz != 640:
        print(f"ROADMIND_IMG_SIZE={args.imgsz}")


if __name__ == "__main__":
    main()
