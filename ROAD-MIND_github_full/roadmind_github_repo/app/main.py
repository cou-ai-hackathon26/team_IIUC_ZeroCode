"""Roadmind web server (FastAPI).

Run with:  uvicorn app.main:app --reload
Then open  http://localhost:8000  (officer dashboard) and  /calibrate  (draw zones).
"""
from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.config import JUNCTIONS_DIR, DATA_DIR, DEFAULT_JUNCTION, STATIC_DIR
from app.junctions import list_junctions, load_junction, save_junction, valid_id
from app.core.voice import speech_mp3
from app.pipeline import PipelineManager
from app.video.autozones import detect_zones
from app.video.source import grab_first_frame

manager = PipelineManager()
OVERRIDE_REASONS = ["VIP movement", "Accident or breakdown", "Officer judgement", "Camera view wrong", "Other"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    manager.stop_all()


app = FastAPI(title="Roadmind", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _junction_or_404(junction_id: str) -> dict:
    if not valid_id(junction_id):
        raise HTTPException(400, "Invalid junction id")
    try:
        return load_junction(junction_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Junction '{junction_id}' not found")


def _pipeline(junction_id: str):
    return manager.get(_junction_or_404(junction_id))


# --- pages ---------------------------------------------------------------
@app.get("/", include_in_schema=False)
def index() -> Response:
    """The page, with the script and style links stamped with their last change time, so a browser
    never mixes a new page with an old saved app.js (that made new buttons show up empty)."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "styles.css"):
        stamp = int((STATIC_DIR / name).stat().st_mtime)
        html = html.replace(f"/static/{name}\"", f"/static/{name}?v={stamp}\"")
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/calibrate", include_in_schema=False)
def calibrate() -> FileResponse:
    return FileResponse(STATIC_DIR / "calibrate.html")


# --- junctions -----------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/junctions")
def junctions() -> dict:
    return {"default": DEFAULT_JUNCTION, "junctions": list_junctions(), "override_reasons": OVERRIDE_REASONS}


@app.get("/api/junctions/{junction_id}")
def junction_detail(junction_id: str) -> dict:
    return _junction_or_404(junction_id)


@app.post("/api/junctions/{junction_id}")
def junction_save(junction_id: str, updates: dict = Body(...)) -> dict:
    """Save zones, source, occupancy, fixed plan or cycle length."""
    if not valid_id(junction_id):
        raise HTTPException(400, "Invalid junction id")
    try:
        junction = save_junction(junction_id, updates)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc))
    manager.reload(junction)
    return junction


@app.get("/api/junctions/{junction_id}/frame")
def junction_frame(junction_id: str) -> Response:
    """First frame of the junction video, for drawing zones on."""
    junction = _junction_or_404(junction_id)
    frame = grab_first_frame(junction.get("source", ""))
    if frame is None:
        raise HTTPException(404, "Could not read a frame from this junction's video source")
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return Response(buf.tobytes(), media_type="image/jpeg")


@app.post("/api/junctions/{junction_id}/autozones")
def autozones(junction_id: str) -> dict:
    """Suggest road zones by watching where vehicles move (the officer still checks and saves)."""
    junction = _junction_or_404(junction_id)
    return detect_zones(junction.get("source", ""), road_names=junction.get("road_names"))


CLIP_TYPES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
MAX_UPLOAD_MB = 500


@app.post("/api/upload")
async def upload_clip(request: Request, name: str, new_junction: bool = False) -> dict:
    """Save an uploaded junction video into data/clips/. Body = the raw file; ?name= its file name."""
    ext = Path(name).suffix.lower()
    if ext not in CLIP_TYPES:
        raise HTTPException(400, "Use an .mp4, .avi, .mov, .mkv or .webm video")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem).strip("_")[:60] or "clip"
    clips = DATA_DIR / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    target, n = clips / f"{stem}{ext}", 2
    while target.exists():  # never overwrite a clip that may be playing
        target, n = clips / f"{stem}_{n}{ext}", n + 1
    part = clips / f"{target.name}.part"
    size = 0
    try:
        with part.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_UPLOAD_MB * 1024 * 1024:
                    raise HTTPException(413, f"Video is larger than {MAX_UPLOAD_MB} MB")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "The file is empty")
        part.replace(target)
    finally:
        part.unlink(missing_ok=True)
    result = {"source": f"data/clips/{target.name}", "size_mb": round(size / 1e6, 1)}
    if new_junction:
        # A new junction for this video. No road zones: Roadmind finds the roads by itself.
        base = re.sub(r"[^a-z0-9_-]+", "_", target.stem.lower()).strip("_")[:40] or "video"
        jid, n = base, 2
        while (JUNCTIONS_DIR / f"{jid}.json").exists():
            jid, n = f"{base}_{n}", n + 1
        save_junction(jid, {"name": Path(name).stem[:60], "source": result["source"], "roads": [],
                            "crossings": [], "fixed_plan": {}, "cycle_seconds": 120})
        result["junction"] = jid
    return result


# --- live state and video ------------------------------------------------
@app.get("/api/state/{junction_id}")
def state(junction_id: str) -> dict:
    return _pipeline(junction_id).latest_state()


@app.get("/api/events/{junction_id}")
async def events(junction_id: str) -> StreamingResponse:
    """Server-Sent Events: the dashboard state, about 4 times per second."""
    pipeline = _pipeline(junction_id)

    async def gen():
        while True:
            yield f"data: {json.dumps(pipeline.latest_state(), ensure_ascii=False, default=str)}\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/stream/{junction_id}")
async def stream(junction_id: str) -> StreamingResponse:
    """Live annotated video as an MJPEG stream (works directly in an <img> tag)."""
    pipeline = _pipeline(junction_id)

    async def frames():
        last = None
        while True:
            jpeg = pipeline.latest_jpeg()
            if jpeg is not None and jpeg is not last:
                last = jpeg
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            await asyncio.sleep(1 / 20)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


# --- officer actions -----------------------------------------------------
@app.post("/api/advice/{junction_id}/refresh")
def advice_refresh(junction_id: str) -> dict:
    _pipeline(junction_id).request_advice()
    return {"ok": True}


@app.post("/api/camera")
def add_camera(body: dict = Body(...)) -> dict:
    """Connect a live camera (phone, webcam or CCTV) as a new junction. The roads are found automatically."""
    source = str(body.get("source", "")).strip()
    if not source:
        raise HTTPException(400, "Type the camera link, for example http://192.168.0.5:8080/video")
    if source.startswith(("http://", "https://")) and source.rstrip("/").count("/") == 2:
        source = source.rstrip("/") + "/video"   # IP Webcam app: the stream is at /video
    name = str(body.get("name") or "Live camera")[:60]
    base = re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_")[:40] or "camera"
    jid, n = base, 2
    while (JUNCTIONS_DIR / f"{jid}.json").exists():
        jid, n = f"{base}_{n}", n + 1
    save_junction(jid, {"name": name, "source": source, "roads": [], "crossings": [],
                        "fixed_plan": {}, "cycle_seconds": 120})
    return {"junction": jid, "source": source}


@app.post("/api/speak")
async def speak(body: dict = Body(...)) -> Response:
    """The advice as Bangla speech (MP3), so it plays in any browser. 503 = use the browser voice."""
    audio = await speech_mp3(str(body.get("text", "")), str(body.get("lang", "bn")))
    if not audio:
        raise HTTPException(503, "Voice service not reachable")
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@app.post("/api/decision")
def decision(body: dict = Body(...)) -> dict:
    """Officer accepts or overrides an advice. Body: {id, action, seconds?, reason?}."""
    action = body.get("action")
    if action not in ("accept", "override"):
        raise HTTPException(400, "action must be 'accept' or 'override'")
    seconds = body.get("seconds")
    if seconds is not None:
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            raise HTTPException(400, "seconds must be a whole number")
        if not -120 <= seconds <= 300:
            raise HTTPException(400, "seconds out of range")
    reason = body.get("reason")
    if action == "override" and reason not in OVERRIDE_REASONS:
        raise HTTPException(400, "Choose a reason for the override")
    result = db.decide(int(body.get("id", 0)), action, seconds, reason)
    if result is None:
        raise HTTPException(404, "Decision not found")
    if result.get("already_decided"):
        raise HTTPException(409, "This advice was already " + result["status"] + ". Wait for the next advice.")
    # the officer's decision goes straight to the junction's traffic lights
    try:
        _pipeline(result["junction"]).apply_decision(result)
    except HTTPException:
        pass
    return result


@app.post("/api/chat/{junction_id}")
def chat_route(junction_id: str, body: dict = Body(...)) -> dict:
    """Ask Roadmind a question. The answer's numbers come from the camera and the advisor rules."""
    message = str(body.get("message", "")).strip()[:500]
    if not message:
        raise HTTPException(400, "Type a question")
    try:
        history = body.get("history") if isinstance(body.get("history"), list) else []
        history = [{"role": str(h.get("role", "")), "text": str(h.get("text", ""))[:600]} for h in history[-8:] if isinstance(h, dict)]
        return _pipeline(junction_id).chat(message, history)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/rain/{junction_id}")
def rain(junction_id: str, body: dict = Body(...)) -> dict:
    """The officer reports heavy rain (Roadmind also notices blur on its own)."""
    pipeline = _pipeline(junction_id)
    pipeline.set_rain(bool(body.get("on")))
    return {"rain": bool(body.get("on"))}


@app.post("/api/plan_ahead/{junction_id}")
def plan_ahead_route(junction_id: str, body: dict = Body(...)) -> dict:
    """A rush (festival, event) is building on one road: green split for the next minutes."""
    road_id = str(body.get("road_id", ""))
    growth = max(-0.9, min(5.0, float(body.get("growth", 0.5))))
    minutes = max(5, min(240, int(body.get("minutes", 20))))
    try:
        return _pipeline(junction_id).make_plan_ahead(road_id, growth, minutes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/emergency/{junction_id}")
def emergency(junction_id: str, body: dict = Body(...)) -> dict:
    """Simulated emergency priority. Body: {road_id} to start, {cancel: true} to stop."""
    pipeline = _pipeline(junction_id)
    if body.get("cancel"):
        pipeline.cancel_emergency()
        return {"ok": True, "active": False}
    road_id = str(body.get("road_id", ""))
    if road_id not in [r["id"] for r in pipeline.junction["roads"]]:
        raise HTTPException(400, "Unknown road")
    pipeline.start_emergency(road_id)
    return {"ok": True, "active": True, "road_id": road_id}


@app.get("/api/log/{junction_id}")
def log(junction_id: str) -> dict:
    _junction_or_404(junction_id)
    return {"decisions": db.recent_decisions(junction_id)}


@app.get("/api/thumb/{name}")
def thumb(name: str) -> FileResponse:
    path = db.thumb_path(name)
    if path is None:
        raise HTTPException(404, "Not found")
    return FileResponse(path, media_type="image/jpeg")
