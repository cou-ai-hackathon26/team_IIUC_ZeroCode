"""The per-junction processing loop.

Every frame (in a background thread):
    read latest frame -> detect + track (every Nth frame) -> per-road stats
    -> people estimate -> confidence check -> draw overlays -> publish state

Once per advice cycle (or when the officer asks, or on emergency):
    advisor -> Bangla/English explanation -> simulated comparison -> forecast
    -> decision log entry (pending until the officer accepts or overrides)

Detection runs live on every run; nothing is pre-recorded or replayed.
"""
from __future__ import annotations

import os
import threading
import time
import traceback

import cv2
import supervision as sv

from app import db
from app.config import CYCLE_SECONDS, DETECT_EVERY, DISPLAY_MAX_FPS, JPEG_QUALITY, MAX_GREEN, MIN_GREEN, MODEL_PATH, SLOW_MODE, STREAM_MAX_WIDTH
from app.core.advisor import AdvisorSettings, advise, plan_for, queue_forecast
from app.core.chat import plan_text
from app.core.explain import explain, bn
from app.core.people import add_people, merged_occupancy, rank
from app.core.rhythm import day_kind, forecast, now_local
from app.core.simulator import compare
from app.junctions import save_junction
from app.video.annotate import annotate
from app.video.autozones import zones_from_tracks
from app.video.confidence import ConfidenceChecker
from app.video.detector import Detector
from app.video.source import VideoSource
from app.video.tracker import JunctionTracker

ADVICE_INTERVAL = int(os.getenv("ROADMIND_ADVICE_INTERVAL", "0"))  # 0 = once per signal cycle
EMERGENCY_SECONDS = 60
WARMUP_SECONDS = 4
COUNTS_EVERY_SECONDS = 60
ALL_FEATURES = ["people", "advice", "log", "confidence", "simulation", "forecast", "emergency"]
# Panels to hide on the dashboard (code stays). Default keeps the demo simple.
# Show everything again with ROADMIND_HIDE_PANELS= (empty) in .env.
HIDDEN = {f.strip() for f in os.getenv("ROADMIND_HIDE_PANELS", "simulation,forecast").split(",") if f.strip()}
FEATURES = [f for f in ALL_FEATURES if f not in HIDDEN]


YELLOW_SECONDS = 3          # fixed safety time after every green (never changed by Roadmind)
ALL_RED_SECONDS = 1         # every light red for a moment before the next road goes green
AUTO_SETUP_SECONDS = 20     # watch this long before finding the roads
AUTO_SETUP_GIVE_UP = 120    # stop trying after this long


def has_zones(junction: dict) -> bool:
    return any(len(r.get("polygon") or []) >= 3 for r in junction.get("roads", []))


class JunctionPipeline:
    def __init__(self, junction: dict) -> None:
        self.junction = junction
        self.source = VideoSource(junction.get("source", ""))
        self.tracker = JunctionTracker(junction["roads"], junction["crossings"])
        self.confidence = ConfidenceChecker()
        self.occupancy = merged_occupancy(junction.get("occupancy"))
        self._lock = threading.Lock()
        self._jpeg: bytes | None = None
        self._state: dict = {"status": "starting", "features": FEATURES}
        self._advice_state: dict | None = None
        self._forecast: dict | None = None
        self._emergency: dict | None = None   # {"road": id, "until": t}
        self._refresh = threading.Event()
        self._running = False
        self._last_frame = None
        self._last_roads: list[dict] = []
        self._last_pedestrians = 0
        # No road zones yet (a new camera): find them automatically from moving traffic.
        self._auto = {"tracks": {}, "first": None, "size": (0, 0)} if not has_zones(junction) else None
        self._auto_status: dict | None = {"status": "finding"} if self._auto else None
        self.source.wait_for_ai = SLOW_MODE and self._auto is not None   # roads known -> normal speed
        self._advice_at: float | None = None   # first advice a few seconds after the roads are found
        # The traffic lights this junction is connected to. They start on the normal fixed plan and
        # change only when the officer accepts or overrides an advice (or starts an emergency).
        self._signal = self._fixed_signal()
        self._signal_before_emergency: dict | None = None
        # Weather switch the officer can turn on (heavy rain), and the "next 20 minutes" plan.
        self._rain = False
        self._plan_waiting_until: float | None = None   # plan shown, waiting for Accept/Override
        self._plan_until: float | None = None           # accepted plan runs until this time
        self._signal_before_plan: dict | None = None

    # --- lifecycle --------------------------------------------------------
    def start(self) -> "JunctionPipeline":
        self.source.start()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        return self

    def stop(self) -> None:
        self._running = False
        self.source.stop()

    def reload(self, junction: dict) -> None:
        """New zones or occupancy values from the officer."""
        self.junction = junction
        self.tracker.set_zones(junction["roads"], junction["crossings"])
        self.occupancy = merged_occupancy(junction.get("occupancy"))
        self._signal = self._fixed_signal()
        self._refresh.set()

    # --- officer actions --------------------------------------------------
    def request_advice(self) -> None:
        self._refresh.set()

    def start_emergency(self, road_id: str) -> None:
        self._emergency = {"road": road_id, "until": time.time() + EMERGENCY_SECONDS}
        if self._signal_before_emergency is None:
            self._signal_before_emergency = self._signal
        greens = dict(self._signal["plan"])
        greens[road_id] = max(greens.get(road_id, MIN_GREEN), MAX_GREEN // 2)
        order = [road_id] + [rid for rid in self._signal["order"] if rid != road_id]
        self._set_signal(greens, order, "emergency")
        self._refresh.set()

    def cancel_emergency(self) -> None:
        self._emergency = None
        if self._signal_before_emergency is not None:
            previous, self._signal_before_emergency = self._signal_before_emergency, None
            self._set_signal(previous["plan"], previous["order"], previous["source"])
        self._refresh.set()

    # --- heavy rain and hidden vehicles ----------------------------------------
    def set_rain(self, on: bool) -> None:
        self._rain = bool(on)
        self._refresh.set()

    def is_raining(self, conf: dict | None = None) -> bool:
        conf = conf or {}
        return self._rain or "Blur / rain" in (conf.get("reasons") or [])

    def hidden_risk(self, roads: list[dict], conf: dict) -> str | None:
        """In heavy rain a bus or rickshaw can be partly hidden behind a truck, so the count on that
        road is too low. Then Roadmind must not tighten the split. Returns the reason, or None."""
        if not self.is_raining(conf):
            return None
        risky = [r for r in roads if r.get("partly_hidden", 0) > 0 or r.get("trucks", 0) > 0]
        if not risky:
            return None
        names = ", ".join(r.get("name", r["id"]) for r in risky)
        return f"Heavy rain: a bus or rickshaw may be hidden behind a truck on {names}"

    # --- plan ahead: any road(s), any crowd change, any length of time --------------
    def make_plan_ahead(self, road_id: str, growth: float, minutes: int) -> dict:
        """The 📅 button: one road's rush."""
        return self.make_plan({road_id: growth}, minutes)

    def make_plan(self, changes: dict[str, float], minutes: int) -> dict:
        with self._lock:
            roads = list(self._det["stats"].get("roads", []))
            conf = self._det["conf"]
        ids = {r["id"] for r in roads}
        changes = {rid: g for rid, g in changes.items() if rid in ids}
        if not changes:
            raise ValueError("Road not found")
        minutes = max(5, min(240, int(minutes)))
        running = (self._signal_before_emergency or self._signal or {}).get("plan") or {}
        fixed_plan = {**self.junction.get("fixed_plan", {}), **running}
        advice = plan_for(roads, fixed_plan, changes, minutes, self._settings())
        careful = self.hidden_risk(roads, conf)
        if careful:  # counts are uncertain: give rush roads more, but cut no road's green on a camera guess
            advice.reasons.append(careful)
            for row in advice.plan:
                if changes.get(row["id"], 0) >= 0 and row["green"] < row["fixed"]:
                    row["green"], row["delta"] = row["fixed"], 0
        advice = advice.to_dict()
        fc = queue_forecast(roads, advice["plan"], changes, None, minutes, self._settings().cycle)
        advice["numbers"]["queue_forecast"] = fc
        text = plan_text(advice, roads, changes, minutes, fc, careful)
        decision_id = db.add_decision(self.junction["id"], advice, text, None)
        with self._lock:
            self._advice_state = {"id": decision_id, **advice, "explanation": text, "simulation": None}
        self._plan_waiting_until = time.time() + 180   # hold normal advice while the officer decides
        return self._advice_state

    # --- ask Roadmind (chat box) ---------------------------------------------
    def chat(self, message: str, history: list[dict] | None = None) -> dict:
        """Any question in Bangla/English. Gemini (if set) reads it and writes a natural reply,
        but every number comes from the camera counts and the advisor rules (checked)."""
        from app.core import chat as c
        history = history or []
        with self._lock:
            roads = list(self._det["stats"].get("roads", []))
            conf = dict(self._det["conf"] or {})
            advice = dict(self._advice_state or {})
        lang = "bn" if c.is_bangla(message) else "en"
        q = c.understand(message, roads, history)
        signal = self.signal_state()
        facts: dict = {
            "roads_now": [{"road": i, "name": r.get("name", r["id"]), "people_waiting": round(r.get("people", 0)),
                           "vehicles": r.get("total_vehicles", 0), "longest_wait_s": round(r.get("longest_wait_s", 0)),
                           "green_now_s": (signal.get("plan") or {}).get(r["id"])} for i, r in enumerate(roads, 1)],
            "lights_running": {"fixed": "normal fixed timer", "accepted": "Roadmind advice accepted by officer",
                               "overridden": "officer's own plan", "emergency": "emergency", "plan_ahead": "a crowd plan"}
                              .get(signal.get("source"), signal.get("source")),
            "camera_confidence": conf.get("level"), "confidence_reasons": conf.get("reasons") or [],
            "rain": self.is_raining(conf), "hidden_vehicle_risk": self.hidden_risk(roads, conf),
            "rules": {"min_green_s": 10, "max_green_s": 60, "max_wait_s": 120, "yellow_s": 3, "cycle_s": 120,
                      "people_per_vehicle": {k: v for k, v in self.occupancy.items()},
                      "officer_decides": "lights change only when the officer presses Accept or Override"},
        }
        if advice:
            facts["last_advice"] = {"text_bn": (advice.get("explanation") or {}).get("bn"),
                                    "reasons": advice.get("reasons"),
                                    "plan": [{"road": r.get("index"), "green_s": r.get("green"), "was_s": r.get("fixed")}
                                             for r in advice.get("plan") or []]}
        reply = {"intent": q["intent"], "understood_by": q["understood_by"], "made_plan": False}
        template = None
        if not roads:
            template = c.status_answer([], {}, conf)
        elif q["intent"] == "plan":
            changes = q.get("changes") or {rid: (q["growth"] if q["growth"] is not None else 0.5) for rid in q["road_ids"]}
            if not changes:
                template = c.which_road(roads)
                facts["need"] = "ask the officer which road (list the roads)"
            else:
                minutes = q["minutes"] or 20
                plan = self.make_plan(changes, minutes)
                fc = plan["numbers"]["queue_forecast"]
                idx = {r["id"]: i for i, r in enumerate(roads, 1)}
                facts["plan"] = {
                    "minutes": max(5, min(240, minutes)), "minutes_assumed": q["minutes"] is None,
                    "crowd_change_percent": {f"Road {idx[rid]}": int(g * 100) for rid, g in changes.items()},
                    "change_assumed": q["growth"] is None and not q.get("changes"),
                    "green": [{"road": r["index"], "name": r.get("name"), "now_s": r["fixed"], "plan_s": r["green"],
                               "change_s": r["delta"]} for r in plan["plan"]],
                    "people_stuck_at_end": {f"Road {idx[rid]}": {"normal_timer": v["fixed"], "with_plan": v["plan"]}
                                            for rid, v in fc["roads"].items()},
                    "lights_alone_not_enough": fc["too_big"],
                    "rain_hold": bool(self.hidden_risk(roads, conf)),
                    "after_plan": "lights go back to the normal timer",
                }
                note_bn = "" if q["minutes"] else "(কত সময় বলেননি, তাই ২০ মিনিট ধরেছি।)\n"
                note_en = "" if q["minutes"] else "(You did not say how long, so I took 20 minutes.)\n"
                template = (note_bn + plan["explanation"]["bn"], note_en + plan["explanation"]["en"])
                reply["made_plan"] = True
        elif q["intent"] == "why":
            ex = advice.get("explanation") or {}
            rows = advice.get("plan") or []
            if advice.get("mode") == "plan_ahead":
                rows = [{"index": i, "people": r.get("people", 0)} for i, r in enumerate(roads, 1)]
            nums_bn = "; ".join(f"রোড {c.bn(r.get('index'))}: {c.bn(round(r.get('people', 0)))} জন" for r in rows)
            nums_en = "; ".join(f"Road {r.get('index')}: {round(r.get('people', 0))} people" for r in rows)
            template = (f"শেষ পরামর্শ: {ex.get('bn', '—')}\nকারণ, অপেক্ষায় থাকা মানুষ: {nums_bn}। যে রাস্তায় বেশি মানুষ (বাসে অনেকজন), "
                        "সেখানে বেশি সবুজ; তবে কোনো রাস্তা ১০ সেকেন্ডের কম পায় না আর কেউ ২ মিনিটের বেশি অপেক্ষা করে না।",
                        f"Last advice: {ex.get('en', '—')}\nBecause of the people waiting: {nums_en}. More people (a bus carries many) "
                        "get more green, but no road gets under 10 s and nobody waits over 2 minutes.")
        elif q["intent"] == "rain":
            risk = self.hidden_risk(roads, conf)
            if risk:
                template = ("বৃষ্টিতে ট্রাকের পেছনে বাস বা রিকশা ঢাকা পড়তে পারে, তাই গোনা নিশ্চিত না। এখন কোনো রাস্তার সবুজ সময় কমানো হবে না।",
                            risk + ". So no road's green time will be cut now.")
            elif self.is_raining(conf):
                template = ("বৃষ্টি চালু আছে, কিন্তু এখন কোনো গাড়ি ট্রাকের পেছনে ঢাকা পড়েনি। স্বাভাবিক পরামর্শ চলবে, তবে সাবধানে।",
                            "Rain is on, but no vehicle is hidden behind a truck now. Normal advice continues, carefully.")
            else:
                template = ("এখন বৃষ্টি ধরা পড়েনি। বৃষ্টি হলে উপরের 🌧 ভারী বৃষ্টি বাটন চাপুন; ছবি ঝাপসা হলে Roadmind নিজেও বুঝে নেয়।",
                            "No rain detected now. If it rains, press 🌧 Heavy rain at the top; Roadmind also notices a blurry picture.")
        elif q["intent"] == "status":
            template = c.status_answer(roads, signal, conf)
        else:
            template = c.help_answer(roads)
        text = c.gemini_reply(message, history, facts, lang)
        reply["answered_by"] = "gemini" if text else "template"
        reply.update(bn=template[0], en=template[1], lang=lang, text=text or (template[0] if lang == "bn" else template[1]))
        return reply

    # --- traffic lights -----------------------------------------------------
    def _fixed_signal(self) -> dict:
        roads = [r for r in self.junction.get("roads", []) if len(r.get("polygon") or []) >= 3]
        fixed = self.junction.get("fixed_plan", {})
        greens = {r["id"]: int(fixed.get(r["id"], MIN_GREEN)) for r in roads}
        return {"plan": greens, "order": list(greens), "source": "fixed", "since": time.time()}

    def _set_signal(self, greens: dict, order: list, source: str) -> None:
        order = [rid for rid in order if rid in greens] + [rid for rid in greens if rid not in order]
        # the change starts now: the first road in the new order turns green straight away
        self._signal = {"plan": {k: int(v) for k, v in greens.items()}, "order": order,
                        "source": source, "since": time.time()}

    def apply_decision(self, decision: dict) -> None:
        """The officer accepted or overrode an advice: change the connected lights now."""
        if self._advice_state and self._advice_state.get("id") == decision.get("id"):
            self._advice_state = {**self._advice_state, "status": decision.get("status")}  # buttons stay off after a reload
        advice = decision.get("advice") or {}
        rows = advice.get("plan") or []
        if not rows:
            return
        if decision.get("status") == "accepted":
            greens = {r["id"]: r["green"] for r in rows}
            source = "accepted"
            if advice.get("mode") == "plan_ahead":
                source = "plan_ahead"
        else:
            greens = {r["id"]: r["fixed"] for r in rows}
            top = advice.get("top") or rows[0]
            change = int(decision.get("chosen_seconds") or 0)
            greens[top["id"]] = min(MAX_GREEN, max(MIN_GREEN, int(top["fixed"]) + change))
            source = "overridden"
        self._signal_before_emergency = None
        if advice.get("mode") == "plan_ahead":
            # the plan runs for its minutes, then the lights go back to the plan they had before
            if self._plan_until is None:
                self._signal_before_plan = self._signal
            minutes = int((advice.get("numbers") or {}).get("plan_minutes", 20))
            self._plan_until = time.time() + minutes * 60
            if decision.get("status") == "overridden":
                source = "overridden"
        self._plan_waiting_until = None
        self._set_signal(greens, advice.get("order") or list(greens), source)

    def signal_state(self) -> dict:
        if not self._signal["plan"]:
            self._signal = self._fixed_signal()
        return {**self._signal, "yellow": YELLOW_SECONDS, "all_red": ALL_RED_SECONDS, "now": time.time()}

    # --- outputs ----------------------------------------------------------
    def latest_jpeg(self) -> bytes | None:
        with self._lock:
            return self._jpeg

    def latest_state(self) -> dict:
        with self._lock:
            state = dict(self._state)
            state["advice"] = self._advice_state
            state["forecast"] = self._forecast
            if self._emergency:
                state["emergency"] = {"road": self._emergency["road"],
                                      "remaining_s": max(0, int(self._emergency["until"] - time.time()))}
            else:
                state["emergency"] = None
            return state

    # --- advice -----------------------------------------------------------
    def _settings(self) -> AdvisorSettings:
        return AdvisorSettings(cycle=int(self.junction.get("cycle_seconds", CYCLE_SECONDS)))

    def _make_advice(self, roads: list[dict], pedestrians: int, conf: dict, frame) -> None:
        settings = self._settings()
        emergency_road = self._emergency["road"] if self._emergency else None
        # compare with the timing the lights are running NOW, so each new advice builds on the last decision
        running = (self._signal_before_emergency or self._signal or {}).get("plan") or {}
        fixed_plan = {**self.junction.get("fixed_plan", {}), **running}
        careful = self.hidden_risk(roads, conf)
        advice = advise(roads, fixed_plan, pedestrians, conf["level"], conf["reasons"], emergency_road, settings,
                        careful=careful).to_dict()
        text = explain(advice, use_llm=False)  # instant template; LLM version follows below

        simulation = None
        if advice["plan"]:
            sim_roads = []
            for r in roads:
                rate = r.get("arrivals_per_min", 0) / 60
                if rate <= 0:  # not enough tracking history yet: assume the queue refills once per cycle
                    rate = r.get("total_vehicles", 0) / max(settings.cycle, 1)
                sim_roads.append({"id": r["id"], "arrival_rate": rate,
                                  "ppv": r.get("people_per_vehicle") or self.occupancy["other"],
                                  "initial_waits": r.get("queued_waits", [])})
            fixed_greens = {r["id"]: int(fixed_plan.get(r["id"], settings.min_green)) for r in roads}
            plan_greens = {row["id"]: row["green"] for row in advice["plan"]}
            simulation = compare(sim_roads, fixed_greens, settings.base_walk,
                                 advice["order"], plan_greens, advice["walk_seconds"])

        thumb = db.save_thumbnail(frame, f"{self.junction['id']}_{int(time.time() * 1000)}") if frame is not None else None
        decision_id = db.add_decision(self.junction["id"], advice, text, thumb)
        with self._lock:
            self._advice_state = {"id": decision_id, **advice, "explanation": text, "simulation": simulation}

        def improve_text() -> None:
            better = explain(advice, use_llm=True)
            if better["source"] == "llm":
                db.update_explanation(decision_id, better)
                with self._lock:
                    if self._advice_state and self._advice_state.get("id") == decision_id:
                        self._advice_state = {**self._advice_state, "explanation": better}
        threading.Thread(target=improve_text, daemon=True).start()

    def _record_counts(self, roads: list[dict]) -> None:
        when = now_local()
        people = sum(r.get("people", 0) for r in roads)
        vehicles = sum(r.get("total_vehicles", 0) for r in roads)
        db.add_counts(self.junction["id"], when.isoformat(), day_kind(when), when.hour * 60 + when.minute,
                      people, vehicles, {r["id"]: r.get("people", 0) for r in roads})
        fc = forecast(db.counts_history(self.junction["id"]), people, when)
        with self._lock:
            self._forecast = fc

    # --- main loop --------------------------------------------------------
    def _loop(self) -> None:
        """Keep the video running: if one frame fails, report it and start again."""
        while self._running:
            try:
                self._run()
            except Exception as exc:  # noqa: BLE001 - never let the live view freeze silently
                traceback.print_exc()
                with self._lock:
                    self._state = {"status": "error", "features": FEATURES, "error": f"Processing error: {type(exc).__name__}: {exc} (restarting)"}
                time.sleep(1)

    def _detect_loop(self, detector: Detector, alive: threading.Event, errors: list) -> None:
        """AI thread: detect + track the newest frame as fast as the CPU allows.

        It runs separately from the video drawing, so the dashboard video stays smooth
        even when YOLO is slow; boxes update at the AI speed ("AI fps").
        """
        last_id, done, times = -1, 0, []
        try:
            while alive.is_set() and self._running:
                frame, frame_id = self.source.read()
                if frame is None or frame_id == last_id or (DETECT_EVERY > 1 and frame_id - last_id < DETECT_EVERY):
                    time.sleep(0.005)
                    continue
                last_id = frame_id
                h, w = frame.shape[:2]
                # in slow mode the video plays slower than real time, so wait times use video time
                t = self.source.video_time if SLOW_MODE and self.source.is_file else time.perf_counter()
                detections = detector.detect(frame)
                tracked, stats = self.tracker.update(detections, w, h, t)
                self.source.consumed(frame_id)
                if self._auto is not None:
                    self._collect_for_auto_setup(detections, w, h)
                confs = detections.confidence
                mean_conf = float(confs.mean()) if confs is not None and len(confs) else None
                stats["mean_confidence"] = round(mean_conf, 3) if mean_conf is not None else None
                stats["roads"] = add_people(stats["roads"], self.occupancy)
                done += 1
                conf = self.confidence.update(frame, len(detections), mean_conf) if done % 3 == 1 else None
                times.append(time.perf_counter())
                times = [x for x in times if times[-1] - x <= 3.0]
                ai_fps = (len(times) - 1) / max(times[-1] - times[0], 1e-6) if len(times) > 1 else 0.0
                with self._lock:
                    self._det = {"tracked": tracked, "stats": stats, "ai_fps": round(ai_fps, 1),
                                 "conf": conf or self._det.get("conf") or self.confidence.last}
        except Exception as exc:  # noqa: BLE001 - handed to the main loop, which restarts
            errors.append(exc)

    def _collect_for_auto_setup(self, detections, w: int, h: int) -> None:
        """Remember where vehicles move; after ~20 s, turn the paths into road zones."""
        auto = self._auto
        # count the video's own time in slow mode (the video plays slower than real time there)
        now = self.source.video_time if SLOW_MODE and self.source.is_file else time.time()
        auto["first"] = auto["first"] or now
        auto["size"] = (w, h)
        types = detections.data.get("type", [])
        for k in range(len(detections)):
            tid = int(detections.tracker_id[k]) if detections.tracker_id is not None else -1
            if tid < 0 or (len(types) and types[k] in ("person", "rider")):
                continue
            x1, y1, x2, y2 = detections.xyxy[k]
            auto["tracks"].setdefault(tid, []).append(((x1 + x2) / 2, y2, x2 - x1, y2 - y1))
        waited = now - auto["first"]
        if waited < (AUTO_SETUP_SECONDS / 2 if SLOW_MODE else AUTO_SETUP_SECONDS):
            return
        roads = zones_from_tracks(auto["tracks"], w, h, road_names=self.junction.get("road_names"))
        if len(roads) == 1 and waited < (AUTO_SETUP_SECONDS * 3 if not SLOW_MODE else AUTO_SETUP_SECONDS * 1.5):
            return  # only one road so far: watch a little longer for traffic from another direction
        if roads:
            cycle = int(self.junction.get("cycle_seconds", CYCLE_SECONDS))
            green = min(MAX_GREEN, max(MIN_GREEN, int(cycle * 0.8 / len(roads))))
            junction = save_junction(self.junction["id"], {
                "roads": roads, "fixed_plan": {r["id"]: green for r in roads}})
            self._auto = None
            self._auto_status = {"status": "done", "roads": len(roads)}
            # same as reload(), but the first advice waits until the new zones have counts
            self.junction = junction
            self.tracker.set_zones(junction["roads"], junction["crossings"])
            self._signal = self._fixed_signal()
            self._advice_at = time.time() + 5
        elif waited > (AUTO_SETUP_GIVE_UP * 3 if SLOW_MODE else AUTO_SETUP_GIVE_UP):
            self._auto = None
            self._auto_status = {"status": "failed",
                                 "message": "Not enough moving vehicles to find the roads."}

    def _run(self) -> None:
        detector = Detector(MODEL_PATH)  # own detector so the tracker's memory starts fresh
        self._det = {"tracked": sv.Detections.empty(), "stats": {"roads": [], "crossings": []},
                     "ai_fps": 0.0, "conf": self.confidence.last}
        alive, errors = threading.Event(), []
        alive.set()
        threading.Thread(target=self._detect_loop, args=(detector, alive, errors), daemon=True).start()
        last_id, last_draw = -1, 0.0
        fps_window: list[float] = []
        started = None
        next_advice = None
        next_counts = time.time() + 30
        try:
            while self._running:
                if errors:
                    raise errors[0]
                frame, frame_id = self.source.read()
                if frame is None or frame_id == last_id or time.perf_counter() - last_draw < 1 / DISPLAY_MAX_FPS:
                    if frame is None and self.source.error:
                        with self._lock:
                            self._state = {"status": "error", "features": FEATURES, "error": self.source.error}
                    time.sleep(0.005)
                    continue
                last_id, last_draw = frame_id, time.perf_counter()
                # slow server: the video waits for the AI only while the roads are being found;
                # after that it plays at normal speed and the AI checks the newest frame it can
                self.source.wait_for_ai = SLOW_MODE and self._auto is not None
                h, w = frame.shape[:2]
                with self._lock:
                    det = self._det
                tracked, stats, conf = det["tracked"], det["stats"], det["conf"]

                pedestrians = sum(c["people"] for c in stats.get("crossings", []))
                image = annotate(frame, tracked, self.tracker.roads, self.tracker.crossings, stats, self.occupancy)
                if STREAM_MAX_WIDTH and image.shape[1] > STREAM_MAX_WIDTH:   # lighter stream on a small server
                    image = cv2.resize(image, (STREAM_MAX_WIDTH, int(image.shape[0] * STREAM_MAX_WIDTH / image.shape[1])),
                                       interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

                fps_window.append(time.perf_counter())
                fps_window = [x for x in fps_window if fps_window[-1] - x <= 2.0]
                fps = (len(fps_window) - 1) / max(fps_window[-1] - fps_window[0], 1e-6) if len(fps_window) > 1 else 0.0

                # --- advice timing: once per cycle, on request, or on emergency changes ---
                now = time.time()
                started = started or now
                if self._emergency and now > self._emergency["until"]:
                    self._emergency = None
                    self._refresh.set()
                interval = ADVICE_INTERVAL or int(self.junction.get("cycle_seconds", CYCLE_SECONDS))
                if self._advice_at and now >= self._advice_at:
                    self._advice_at = None
                    self._refresh.set()
                if self._plan_until and now >= self._plan_until:   # the 20-minute plan is over
                    self._plan_until = None
                    if self._signal_before_plan:
                        before, self._signal_before_plan = self._signal_before_plan, None
                        self._set_signal(before["plan"], before["order"], before["source"])
                    self._refresh.set()
                if self._plan_waiting_until and now >= self._plan_waiting_until:
                    self._plan_waiting_until = None
                    self._refresh.set()
                due = next_advice is None and now - started >= WARMUP_SECONDS and det["ai_fps"] > 0
                due = due or (next_advice is not None and now >= next_advice) or self._refresh.is_set()
                plan_busy = bool(self._plan_until or self._plan_waiting_until)
                if due and plan_busy and not self._refresh.is_set():  # a 20-minute plan is shown or running
                    due = False
                    next_advice = now + interval
                if due and (self._auto is not None or self._advice_at):  # finding roads: no advice yet
                    due = False
                    next_advice = None
                    self._refresh.clear()
                if due:
                    self._refresh.clear()
                    try:
                        self._make_advice(stats["roads"], pedestrians, conf, frame)
                    except Exception as exc:  # never let one bad advice stop the video
                        with self._lock:
                            self._advice_state = {"error": f"Advice failed: {type(exc).__name__}: {exc}"}
                    next_advice = now + interval
                if now >= next_counts:
                    next_counts = now + COUNTS_EVERY_SECONDS
                    threading.Thread(target=self._record_counts, args=(stats["roads"],), daemon=True).start()

                state = {
                    "status": "running",
                    "junction": {"id": self.junction["id"], "name": self.junction.get("name")},
                    "frame_size": [w, h],
                    "fps": round(fps, 1),
                    "ai_fps": det["ai_fps"],
                    "supported_types": detector.supported_types,
                    "occupancy": self.occupancy,
                    "features": FEATURES,
                    "auto_setup": self._auto_status,
                    "signal": self.signal_state(),
                    "rain": self.is_raining(conf),
                    "rain_switch": self._rain,
                    "hidden_risk": self.hidden_risk(stats.get("roads", []), conf),
                    "plan_until": self._plan_until,
                    "confidence": conf,
                    "pedestrians_waiting": pedestrians,
                    "rank_people": rank(stats["roads"], "people"),
                    "rank_vehicles": rank(stats["roads"], "total_vehicles"),
                    "next_advice_in_s": max(0, int(next_advice - now)) if next_advice else None,
                    **stats,
                }
                with self._lock:
                    if ok:
                        self._jpeg = buf.tobytes()
                    self._state = state
        finally:
            alive.clear()


class PipelineManager:
    """Keeps one running pipeline (the selected junction) to save CPU."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: JunctionPipeline | None = None

    def get(self, junction: dict) -> JunctionPipeline:
        with self._lock:
            if self._active is None or self._active.junction["id"] != junction["id"]:
                if self._active is not None:
                    self._active.stop()
                self._active = JunctionPipeline(junction).start()
            return self._active

    def reload(self, junction: dict) -> None:
        with self._lock:
            if self._active is not None and self._active.junction["id"] == junction["id"]:
                if self._active.junction.get("source") != junction.get("source"):
                    # new camera or file: restart the video and the tracker
                    self._active.stop()
                    self._active = JunctionPipeline(junction).start()
                else:
                    self._active.reload(junction)

    def stop_all(self) -> None:
        with self._lock:
            if self._active is not None:
                self._active.stop()
                self._active = None
