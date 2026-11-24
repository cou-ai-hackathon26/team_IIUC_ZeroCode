"""Rebuild Roadmind's folder layout when the files were uploaded flat (all in one folder).

Uploading through the GitHub website (especially from a phone) can drop the folders,
so app/main.py ends up as main.py at the top. The Dockerfile runs this script during
the build: if app/main.py already exists it does nothing; otherwise it moves every
known file to the folder it belongs in.
"""
from __future__ import annotations

import glob
import os
import shutil

ROOT = os.path.dirname(os.path.abspath(__file__))

PLACES = {
    "app": ["config.py", "db.py", "junctions.py", "main.py", "pipeline.py"],
    "app/core": ["advisor.py", "explain.py", "people.py", "rhythm.py", "simulator.py"],
    "app/video": ["annotate.py", "autozones.py", "confidence.py", "detector.py", "source.py", "tracker.py"],
    "app/static": ["app.js", "calibrate.html", "index.html", "styles.css"],
    "config": ["events.json"],
    "scripts": ["evaluate_counts.py", "offline.py", "record_counts.py", "speed_up.py"],
}
APP_INIT = '''"""Roadmind — AI traffic-signal advisor."""
import warnings

warnings.filterwarnings("ignore", category=FutureWarning, module=r"supervision(\\..*)?")
'''


def here(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


def move(name: str, folder: str, new_name: str | None = None) -> None:
    src = here(name)
    if os.path.isfile(src):
        os.makedirs(here(folder), exist_ok=True)
        shutil.move(src, here(folder, new_name or name))
        print(f"  {name} -> {folder}/{new_name or name}")


def main() -> None:
    if os.path.isfile(here("app", "main.py")):
        print("fix_layout: folders already correct, nothing to do")
        return
    if not os.path.isfile(here("main.py")):
        print("fix_layout: main.py not found anywhere — upload the project files")
        return
    print("fix_layout: files were uploaded without folders, rebuilding the layout:")
    for folder, names in PLACES.items():
        for name in names:
            move(name, folder)
    for path in glob.glob(here("*.woff2")):
        move(os.path.basename(path), "app/static/fonts")
    for path in glob.glob(here("test_*.py")):
        move(os.path.basename(path), "tests")
    # package markers (their contents do not matter, except app/__init__.py)
    for folder in ("app/core", "app/video", "tests"):
        open(here(folder, "__init__.py"), "a").close()
    with open(here("app", "__init__.py"), "w", encoding="utf-8") as f:
        f.write(APP_INIT)
    # junctions: a ready-made junction file with zones becomes the default "demo"
    os.makedirs(here("junctions"), exist_ok=True)
    if os.path.isfile(here("testclip.json")):
        move("testclip.json", "junctions", "demo.json")
        if os.path.isfile(here("demo.json")):
            os.remove(here("demo.json"))
    else:
        move("demo.json", "junctions")
    # videos go to data/clips (keep their names; demo.json points at them)
    for path in glob.glob(here("*.mp4")):
        move(os.path.basename(path), "data/clips")
    for folder in ("data/clips", "data/ground_truth", "models"):
        os.makedirs(here(folder), exist_ok=True)
    print("fix_layout: done")


if __name__ == "__main__":
    main()
