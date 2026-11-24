# Roadmind — start here (local)

## First time (needs internet once)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Optional: open `.env` and paste your Gemini key after `GEMINI_API_KEY=`.

## Every time
```
.venv\Scripts\activate
uvicorn app.main:app --reload
```
Open http://localhost:8000 — the demo junction video (`data/clips/demo.mp4`) plays with its road zones already drawn. To use your own video, replace that file or upload one on the calibration page.

## Switch videos
- Use the **Junction** dropdown at the top left.
- Your own video: press **⬆ Upload video** at the top of the dashboard and pick the file.
  It opens as a new junction, and Roadmind finds the roads by itself in about 20 seconds.

## Faster on a laptop (optional)
```
pip install openvino
python scripts/speed_up.py
```
Put the line it prints into `.env`, then restart.

## Upload to GitHub correctly
Upload the FOLDERS, not loose files. In GitHub Desktop: copy everything from this folder into your repo folder, commit, push.
In the browser: drag the folders (`app`, `config`, `data`, `deploy`, `junctions`, `models`, `scripts`, `tests`) and the top files onto **Add file → Upload files**.
On GitHub you must see `app/main.py` — not `main.py` at the top.
