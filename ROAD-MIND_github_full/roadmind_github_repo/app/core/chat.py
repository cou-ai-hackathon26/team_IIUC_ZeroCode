"""Ask Roadmind: the officer types a question in Bangla, Banglish or English.

Two steps, kept apart on purpose:
1. Understand the question -> a small "intent" (what is asked, which road, how big a rush, how long).
   Gemini does this when a key is set; simple keyword rules do it offline or when Gemini fails.
2. Answer from Roadmind's own numbers (camera counts, the advisor rules). The language model never
   makes up a number: every number in the answer comes from the camera or from the advisor.
"""
from __future__ import annotations

import json
import logging
import re

from app.config import GEMINI_API_KEY
from app.core.explain import GEMINI_MODEL, LLM_TIMEOUT_S, _pool, bn

log = logging.getLogger(__name__)

INTENTS = ("plan", "status", "why", "rain", "help")
LESS_WORDS = ["less", "fewer", "decrease", "drop", "empty", "kombe", "kome", "komte", "কমবে", "কমে", "কমতে", "ফাঁকা", "faka"]
NUM_WORDS = {"এক": 1, "দুই": 2, "তিন": 3, "চার": 4, "পাঁচ": 5, "ek": 1, "dui": 2, "tin": 3, "char": 4, "pach": 5,
             "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

PLAN_WORDS = ["festival", "rush", "event", "mela", "match", "eid", "puja", "crowd", "plan", "next", "increase",
              "school", "office", "chuti", "utshob", "utsob", "utsab", "bhir", "vir", "barbe", "barle", "agami", "porer",
              "উৎসব", "ভিড়", "ভীড়", "মেলা", "ঈদ", "পূজা", "পরের", "আগামী", "বাড়বে", "বাড়লে", "ছুটি", "পরিকল্পনা", "অনুষ্ঠান"]
WHY_WORDS = ["why", "keno", "kno", "কেন"]
RAIN_WORDS = ["rain", "brishti", "bristi", "hidden", "lukano", "বৃষ্টি", "লুকানো", "ঢাকা"]
STATUS_WORDS = ["now", "status", "situation", "how many", "ekhon", "koto", "obostha", "kemon", "lights", "signal",
                "এখন", "কত", "অবস্থা", "কেমন", "বাতি", "সিগন্যাল", "মানুষ", "গাড়ি"]


def is_bangla(text: str) -> bool:
    if re.search(r"[ঀ-৿]", text):
        return True
    banglish = ["ki", "koto", "keno", "ekhon", "hobe", "korbo", "kemon", "rasta", "rastay", "utshob", "bhir", "agami", "porer",
                "dao", "bolo", "hoye", "jabe", "jaabe", "ashbe", "asbe", "ache", "ase", "er", "e", "te", "theke", "kom", "beshi",
                "faka", "mela", "chuti", "ghonta", "minit", "korte", "lagbe", "amar", "ami", "naki", "tahole", "taile"]
    words = re.findall(r"[a-z]+", text.lower())
    return sum(w in banglish for w in words) >= 1


def _has(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def find_roads(text: str, roads: list[dict]) -> list[str]:
    """Every road the question names: 'road 1 ar road 3', 'রোড ১ ও ২', or road names."""
    t = text.lower().translate(BN_DIGITS)
    found: list[str] = []
    for m in re.finditer(r"(?:road|rasta|rastay|রোড|রাস্তা|lane)\s*(?:no\.?|নং|নম্বর)?\s*(\d+(?:\s*(?:,|and|ar|আর|ও|o|&)\s*\d+)*)", t):
        for n in re.findall(r"\d+", m.group(1)):
            if 1 <= int(n) <= len(roads) and roads[int(n) - 1]["id"] not in found:
                found.append(roads[int(n) - 1]["id"])
    one = find_road(text, roads)
    if one and one not in found:
        found.append(one)
    return found


def find_road(text: str, roads: list[dict]) -> str | None:
    """'road 2', 'রোড ২', 'রাস্তা ২', '2 no road', or the road's name."""
    t = text.lower().translate(BN_DIGITS)
    m = re.search(r"(?:road|rasta|rastay|রোড|রাস্তা|lane)\s*(?:no\.?|নং|নম্বর)?\s*(\d+)", t) or \
        re.search(r"(\d+)\s*(?:no|নং|নম্বর)?\s*(?:road|rasta|রোড|রাস্তা)", t)
    if m:
        i = int(m.group(1))
        if 1 <= i <= len(roads):
            return roads[i - 1]["id"]
    for r in roads:                                     # by name: "Oncoming lane", "Station Road"
        name = str(r.get("name", "")).lower()
        if name and name in t:
            return r["id"]
    for r in roads:                                     # one strong word of the name, e.g. "station"
        for word in re.findall(r"[a-zঀ-৿]{4,}", str(r.get("name", "")).lower()):
            if word not in ("road", "lane", "from", "the") and word in t:
                return r["id"]
    return None


def find_growth(text: str) -> float | None:
    t = text.lower().translate(BN_DIGITS)
    m = re.search(r"(\d+)\s*(?:%|percent|শতাংশ|parcent)", t)
    if m:
        return min(3.0, int(m.group(1)) / 100)
    if _has(t, ["triple", "3 gun", "তিনগুণ", "তিন গুণ"]):
        return 2.0
    if _has(t, ["double", "2 gun", "digun", "দ্বিগুণ", "দিগুণ", "দুই গুণ", "অনেক", "onek", "huge", "big", "heavy", "boro", "বড়"]):
        return 1.0
    if _has(t, ["little", "small", "ektu", "একটু", "অল্প", "olpo"]):
        return 0.3
    return None


def find_minutes(text: str) -> int | None:
    t = text.lower().translate(BN_DIGITS)
    m = re.search(r"(\d+)\s*(?:min|minute|minit|মিনিট)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:hour|hours|ghonta|ঘণ্টা|ঘন্টা)", t)
    if m:
        return int(float(m.group(1)) * 60)
    m = re.search(r"(এক|দুই|তিন|চার|পাঁচ|ek|dui|tin|char|pach|one|two|three|four|five)\s*(?:hour|hours|ghonta|ঘণ্টা|ঘন্টা)", t)
    if m:
        return NUM_WORDS[m.group(1)] * 60
    if _has(t, ["half hour", "half an hour", "আধা ঘণ্টা", "আধ ঘণ্টা", "adha ghonta"]):
        return 30
    if _has(t, ["an hour", "one hour", "ek ghonta", "এক ঘণ্টা", "এক ঘন্টা"]):
        return 60
    return None


def understand_by_rules(text: str, roads: list[dict]) -> dict:
    t = text.lower()
    growth = find_growth(text)
    if _has(t, LESS_WORDS):
        growth = -abs(growth) if growth is not None else -0.5
        growth = max(growth, -0.9)
    if _has(t, PLAN_WORDS) or growth is not None:
        intent = "plan"
    elif _has(t, RAIN_WORDS):
        intent = "rain"
    elif _has(t, WHY_WORDS):
        intent = "why"
    elif _has(t, STATUS_WORDS) or find_road(text, roads):
        intent = "status"
    else:
        intent = "help"
    road_ids = find_roads(text, roads)
    return {"intent": intent, "road_id": road_ids[0] if road_ids else None, "road_ids": road_ids,
            "growth": growth, "minutes": find_minutes(text), "understood_by": "rules"}


# ---------- Gemini: (1) read the question, (2) write the reply from Roadmind's facts ----------
def _gemini(prompt: str) -> str:
    from google import genai
    return (genai.Client(api_key=GEMINI_API_KEY).models.generate_content(model=GEMINI_MODEL, contents=prompt).text or "").strip()


def _history_text(history: list[dict]) -> str:
    lines = []
    for h in (history or [])[-8:]:
        who = "Officer" if h.get("role") == "user" else "Roadmind"
        lines.append(f"{who}: {str(h.get('text', ''))[:400]}")
    return "\n".join(lines)


def _ask_gemini(text: str, roads: list[dict], history: list[dict] | None = None) -> dict:
    road_list = "; ".join(f"Road {i}: {r.get('name', r['id'])}" for i, r in enumerate(roads, 1))
    prompt = (
        "You read messages from a traffic police officer in Bangladesh (Bangla, Banglish or English) to Roadmind, "
        "a traffic-signal advisor. Do not answer. Only fill this JSON and reply with the JSON alone:\n"
        '{"intent": "plan" | "status" | "why" | "rain" | "help", '
        '"changes": [{"road": <road number>, "percent": <how much the crowd on that road will change, e.g. 50, 100, -40>}], '
        '"minutes": <how long the plan should run, a number, or null>}\n'
        "plan = the officer expects the crowd on one or more roads to grow or fall (festival, mela, Eid, puja, match, "
        "school or office time, rally, road closed nearby, VIP, anything) and wants a green split for some time ahead. "
        "status = how things are now. why = why Roadmind advised something. rain = rain or hidden vehicles. "
        "help = greetings, other questions. 'double' = 100, 'triple' = 200, 'a little' = 30, 'a lot' = 100, "
        "'half' = -50 when it falls. If the crowd change is not said, use 50 (or -50 if it falls). "
        "If only time of day is given (e.g. 'till 5 pm'), leave minutes null. Use the earlier chat to fill gaps.\n"
        f"Roads at this junction: {road_list}\nEarlier chat:\n{_history_text(history or [])}\nMessage: {text}"
    )
    data = json.loads(re.search(r"\{.*\}", _gemini(prompt), re.S).group(0))
    intent = data.get("intent") if data.get("intent") in INTENTS else "help"
    road_ids, growth = [], None
    changes = {}
    for ch in data.get("changes") or []:
        n, pct = ch.get("road"), ch.get("percent")
        if isinstance(n, (int, float)) and 1 <= int(n) <= len(roads):
            g = max(-0.9, min(5.0, float(pct) / 100)) if isinstance(pct, (int, float)) else 0.5
            changes[roads[int(n) - 1]["id"]] = g
            road_ids.append(roads[int(n) - 1]["id"])
            growth = g if growth is None else growth
    minutes = data.get("minutes")
    minutes = int(minutes) if isinstance(minutes, (int, float)) and minutes > 0 else None
    return {"intent": intent, "road_id": road_ids[0] if road_ids else None, "road_ids": road_ids,
            "changes": changes, "growth": growth, "minutes": minutes, "understood_by": "gemini"}


def understand(text: str, roads: list[dict], history: list[dict] | None = None) -> dict:
    rules = understand_by_rules(text, roads)
    if not GEMINI_API_KEY:
        return rules
    try:
        g = _pool.submit(_ask_gemini, text, roads, history).result(timeout=LLM_TIMEOUT_S + 4)
        if g["intent"] == "plan" and not g["road_ids"] and rules["road_ids"]:
            g["road_ids"], g["road_id"] = rules["road_ids"], rules["road_id"]
        if g["minutes"] is None:
            g["minutes"] = rules["minutes"]
        return g
    except Exception as exc:  # no internet, quota, bad JSON -> rules
        log.info("Gemini chat skipped: %s", type(exc).__name__)
        return rules


_NUM = re.compile(r"\d+(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    out = set()
    for n in _NUM.findall(str(text).translate(BN_DIGITS)):
        out.add(n)
        if "." in n:
            out.add(str(round(float(n))))
    return out


def numbers_ok(reply: str, allowed_text: str) -> bool:
    """Every number in Gemini's reply must come from Roadmind's facts (or the officer's own words)."""
    allowed = _numbers(allowed_text) | {str(i) for i in range(0, 11)} | {"20", "30", "60", "120", "40", "100"}
    return all(n in allowed for n in _numbers(reply))


def gemini_reply(message: str, history: list[dict], facts: dict, lang: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    facts_text = json.dumps(facts, ensure_ascii=False)
    prompt = (
        "You are Roadmind, a friendly assistant for a traffic police officer at a junction in Bangladesh. "
        "Talk like a helpful chat assistant (like ChatGPT): natural, warm, clear, short paragraphs or a few bullet points. "
        + ("Reply in simple Bangla (Bangla script, Bangla digits). " if lang == "bn" else "Reply in simple English. ")
        + "Rules: use ONLY the numbers in FACTS; never invent or estimate a number yourself. "
        "If FACTS has a plan, explain it road by road (green seconds now -> in the plan), the people stuck with the normal "
        "timer vs with the plan, any warning, and say the officer must press Accept on the advice card to change the lights "
        "(or Override). The officer always decides. If something is not in FACTS, say you don't know it from the camera. "
        "If a question is not about this junction's traffic, answer briefly and bring it back to traffic. "
        "No markdown headings, no tables.\n\n"
        f"FACTS: {facts_text}\n\nEarlier chat:\n{_history_text(history)}\n\nOfficer: {message}\nRoadmind:"
    )
    try:
        reply = _pool.submit(_gemini, prompt).result(timeout=LLM_TIMEOUT_S + 8)
    except Exception as exc:
        log.info("Gemini reply skipped: %s", type(exc).__name__)
        return None
    allowed = facts_text + " " + message + " " + _history_text(history)
    if not reply or not numbers_ok(reply, allowed):
        log.info("Gemini reply dropped: a number not in the facts")
        return None
    return reply.replace("**", "")


# ---------- answers from Roadmind's own numbers (also the offline fallback) ----------
def road_index(roads: list[dict], road_id: str) -> int:
    return next((i for i, r in enumerate(roads, 1) if r["id"] == road_id), 0)


def plan_text(advice: dict, roads: list[dict], changes: dict[str, float], minutes: int, fc: dict,
              careful: str | None) -> dict:
    """The plan in plain words, road by road."""
    idx = {r["id"]: i for i, r in enumerate(roads, 1)}
    bn_lines = [f"পরের {bn(minutes)} মিনিটের পরিকল্পনা:"]
    en_lines = [f"Plan for the next {minutes} minutes:"]
    for rid, g in changes.items():
        word_bn = "বাড়বে" if g >= 0 else "কমবে"
        bn_lines.append(f"ধরে নিয়েছি রোড {bn(idx.get(rid, 0))}-এ ভিড় {bn(abs(int(g * 100)))}% {word_bn}।")
        en_lines.append(f"Assumed: the crowd on Road {idx.get(rid, 0)} {'grows' if g >= 0 else 'falls'} by {abs(int(g * 100))}%.")
    for row in advice.get("plan", []):
        d = row["delta"]
        sign = "+" if d > 0 else ""
        bn_lines.append(f"• রোড {bn(row['index'])} ({row.get('name', '')}): সবুজ {bn(row['fixed'])} → {bn(row['green'])} সেকেন্ড"
                        + (f" ({sign}{bn(d)})" if d else " (একই)"))
        en_lines.append(f"• Road {row['index']} ({row.get('name', '')}): green {row['fixed']} → {row['green']} s"
                        + (f" ({sign}{d})" if d else " (same)"))
    main = fc.get("main")
    if main:
        q = fc["roads"][main]
        bn_lines.append(f"স্বাভাবিক টাইমারে {bn(minutes)} মিনিট পর রোড {bn(idx.get(main, 0))}-এ প্রায় {bn(q['fixed'])} জন আটকে থাকবে; "
                        f"এই পরিকল্পনায় প্রায় {bn(q['plan'])} জন।")
        en_lines.append(f"With the normal timer about {q['fixed']} people would be stuck on Road {idx.get(main, 0)} after "
                        f"{minutes} minutes; with this plan about {q['plan']}.")
    if careful:
        bn_lines.append("🌧 বৃষ্টিতে কিছু গাড়ি ঢাকা পড়তে পারে, তাই কোনো রাস্তার সবুজ সময় ক্যামেরার গোনার ভিত্তিতে কমানো হয়নি।")
        en_lines.append("🌧 Some vehicles may be hidden in the rain, so no road's green was cut on the camera count.")
    if fc.get("too_big"):
        bn_lines.append("⚠ শুধু বাতি দিয়ে এই ভিড় সামলানো যাবে না: বাড়তি পুলিশ বা বিকল্প পথ লাগবে।")
        en_lines.append("⚠ The lights alone cannot handle this rush: send extra police or use another route.")
    bn_lines.append(f"পরামর্শ কার্ডে Accept চাপলে বাতি {bn(minutes)} মিনিট এভাবে চলবে, তারপর স্বাভাবিক টাইমারে ফিরবে।")
    en_lines.append(f"Press Accept on the advice card and the lights run this for {minutes} minutes, then go back to normal.")
    return {"bn": "\n".join(bn_lines), "en": "\n".join(en_lines), "source": "template"}


def status_answer(roads: list[dict], signal: dict, conf: dict) -> tuple[str, str]:
    if not roads:
        return ("এখনো কোনো রাস্তা পাওয়া যায়নি। ভিডিও বা ক্যামেরা চালু করুন।",
                "No roads found yet. Start a video or a camera.")
    bn_lines, en_lines = ["এখন মোড়ের অবস্থা:"], ["Right now at the junction:"]
    for i, r in enumerate(roads, 1):
        people, veh = round(r.get("people", 0)), r.get("total_vehicles", 0)
        wait = round(r.get("longest_wait_s", 0))
        green = (signal.get("plan") or {}).get(r["id"])
        bn_lines.append(f"• রোড {bn(i)} ({r.get('name', '')}): প্রায় {bn(people)} জন মানুষ, {bn(veh)}টি গাড়ি, "
                        f"সবচেয়ে বেশি অপেক্ষা {bn(wait)} সেকেন্ড; এখন সবুজ {bn(green)} সেকেন্ড।")
        en_lines.append(f"• Road {i} ({r.get('name', '')}): about {people} people, {veh} vehicles, longest wait {wait} s; "
                        f"green now {green} s.")
    level = conf.get("level", "High")
    level_bn = {"High": "বেশি", "Medium": "মাঝারি", "Low": "কম"}.get(level, level)
    bn_lines.append(f"ক্যামেরার নিশ্চয়তা: {level_bn}।")
    en_lines.append(f"Camera confidence: {level}.")
    return "\n".join(bn_lines), "\n".join(en_lines)


def help_answer(roads: list[dict]) -> tuple[str, str]:
    return ("আমি এই মোড়ের ট্রাফিক নিয়ে সাহায্য করতে পারি। যেমন জিজ্ঞেস করতে পারেন:\n"
            "• \"রোড ২-এ মেলার ভিড় আসছে, দ্বিগুণ হবে, পরের ১ ঘণ্টা কী করব?\"\n"
            "• \"অফিস ছুটির পর রোড ১ আর ৩-এ ভিড় বাড়বে, ৪৫ মিনিটের প্ল্যান দাও\"\n"
            "• \"রোড ২ ফাঁকা হয়ে যাবে, তাহলে কী করব?\"\n"
            "• \"এখন কোন রাস্তায় কত মানুষ?\", \"এই পরামর্শ কেন?\", \"বৃষ্টিতে কী করব?\"",
            "I can help with this junction's traffic. For example:\n"
            "• \"A mela crowd is coming on Road 2, double, what for the next hour?\"\n"
            "• \"After office time Road 1 and 3 get busy, give me a 45-minute plan\"\n"
            "• \"Road 2 will get empty, what then?\"\n"
            "• \"How many people on each road now?\", \"Why this advice?\", \"What about the rain?\"")


def which_road(roads: list[dict]) -> tuple[str, str]:
    names_bn = ", ".join(f"রোড {bn(i)} ({r.get('name', '')})" for i, r in enumerate(roads, 1))
    names_en = ", ".join(f"Road {i} ({r.get('name', '')})" for i, r in enumerate(roads, 1))
    return (f"কোন রাস্তায় ভিড় বদলাবে? যেমন লিখুন \"রোড ১-এ ভিড়\"। রাস্তাগুলো: {names_bn}",
            f"Which road will the crowd change on? For example \"rush on Road 1\". Roads: {names_en}")
