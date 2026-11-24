"""Bangla (and English) explanation of the advice.

The NUMBERS always come from the advisor. Text is produced in two steps:
1. a template sentence is ready instantly (works offline);
2. if a Gemini key is set, the LLM rephrases it more naturally. The reply is
   accepted only if it contains the same road number and seconds; otherwise
   the template is kept. So the explanation can never change the decision.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os

from app.config import GEMINI_API_KEY

log = logging.getLogger("roadmind.explain")
GEMINI_MODEL = os.getenv("ROADMIND_GEMINI_MODEL", "gemini-3.8-flash")
LLM_TIMEOUT_S = 3.0

_BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
REASON_BN = {
    "Dark": "আলো খুব কম",
    "Blur / rain": "ছবি ঝাপসা (বৃষ্টি হতে পারে)",
    "View blocked": "ক্যামেরার দৃশ্য ঢাকা",
    "Low detection confidence": "গাড়ি চেনার নিশ্চয়তা কম",
}


def bn(value) -> str:
    """Write a number with Bangla digits (e.g. 15 -> ১৫)."""
    return str(value).translate(_BN_DIGITS)


def template_texts(advice: dict) -> tuple[str, str]:
    """Return (Bangla, English) template sentences for an advice dict."""
    mode, top = advice.get("mode"), advice.get("top")
    ext = advice.get("walk_extension", 0)
    if mode == "keep_fixed":
        reasons = [r for r in advice.get("reasons", []) if r != "Low confidence"]
        if not advice.get("plan"):
            return ("রাস্তাগুলো এখনো খুঁজে পাওয়া যায়নি।", "The roads have not been found yet.")
        why_bn = ", ".join(REASON_BN.get(r, r) for r in reasons) or "নিশ্চয়তা কম"
        why_en = ", ".join(reasons) or "low confidence"
        return (f"এখন নিশ্চিত নই ({why_bn}), তাই আগের নির্দিষ্ট টাইমার চালু রাখুন।",
                f"Not confident right now ({why_en}), so keep the fixed timer.")
    if mode == "emergency" and top:
        return (f"জরুরি অবস্থা: রোড {bn(top['index'])}-এ অ্যাম্বুলেন্সের জন্য আগে {bn(top['green'])} সেকেন্ড সবুজ বাতি দিন।",
                f"Emergency: give Road {top['index']} green first for {top['green']} seconds for the ambulance.")
    if mode == "plan_ahead" and top:
        mins = advice.get("numbers", {}).get("plan_minutes", 20)
        if top["delta"] > 0:
            return (f"আগামী {bn(mins)} মিনিট রোড {bn(top['index'])}-এ ভিড় বাড়বে, তাই প্রতিবার {bn(top['delta'])} সেকেন্ড বেশি সবুজ বাতি দিন।",
                    f"For the next {mins} minutes the rush on Road {top['index']} will grow, so give it {top['delta']} seconds more green each cycle.")
        return (f"আগামী {bn(mins)} মিনিট রোড {bn(top['index'])}-এ ভিড় বাড়লেও এখনকার সবুজ সময়ই যথেষ্ট।",
                f"Even with the rush on Road {top['index']}, the current green time is enough for the next {mins} minutes.")
    if "Holding the current split: counts are uncertain" in advice.get("reasons", []):
        return ("বৃষ্টিতে কিছু গাড়ি আংশিক ঢাকা পড়েছে, তাই গোনা নিশ্চিত নয়। সবুজ সময় কমানো-বাড়ানো হচ্ছে না, এখনকার ভাগই চালু রাখুন।",
                "Some vehicles are partly hidden in the rain, so the counts are uncertain. Keep the current split; no road's green is cut.")
    if not top and "No vehicles in the road zones" in advice.get("reasons", []):
        bn_text = "রাস্তার জোনে এখন কোনো যানবাহন নেই, তাই আগের টাইমিং চালু রাখুন।"
        en_text = "No vehicles in the road zones right now, so keep the current timing."
    elif top:
        bn_text = f"রোড {bn(top['index'])}-এ বেশি মানুষ অপেক্ষা করছে, তাই {bn(top['delta'])} সেকেন্ড বেশি সবুজ বাতি দিন।"
        en_text = f"More people are waiting on Road {top['index']}, so give it {top['delta']} seconds more green."
    else:
        bn_text = "এখনকার টাইমিং ঠিক আছে, কোনো পরিবর্তন দরকার নেই।"
        en_text = "The current timing fits the traffic; no change needed."
    if ext:
        bn_text += f" পথচারীদের জন্য {bn(ext)} সেকেন্ড বেশি হাঁটার সময় দিন।"
        en_text += f" Give pedestrians {ext} extra seconds to cross."
    return bn_text, en_text


def _required_tokens(advice: dict) -> list[str]:
    """Numbers the LLM reply must contain (in Bangla digits) to be accepted."""
    top = advice.get("top")
    if not top or advice.get("mode") == "keep_fixed":
        return []
    if advice.get("mode") == "plan_ahead":
        return [bn(top["index"])] + ([bn(top["delta"])] if top["delta"] > 0 else [])
    seconds = top["green"] if advice.get("mode") == "emergency" else top["delta"]
    return [bn(top["index"]), bn(seconds)]


def validate(reply: str, advice: dict) -> bool:
    """Accept an LLM sentence only if it is short and keeps the exact numbers."""
    reply = (reply or "").strip()
    if not reply or len(reply) > 220:
        return False
    tokens = _required_tokens(advice)
    if not tokens:  # a "no change" sentence must not invent any numbers
        return not any(ch.isdigit() for ch in reply)
    return all(token in reply for token in tokens)


def _ask_gemini(template_bn: str, advice: dict) -> str:
    from google import genai  # imported lazily so the app runs without the package/key

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = (
        "You help a traffic police officer in Bangladesh. Rewrite this advice as ONE short, polite, "
        "natural Bangla sentence (max 25 words). Keep every number exactly as written in Bangla digits. "
        "Do not add any new facts or numbers. Reply with the sentence only.\n\n"
        f"Advice: {template_bn}"
    )
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    return (response.text or "").strip().strip('"“”')


_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def explain(advice: dict, use_llm: bool = True) -> dict:
    """Return {'bn', 'en', 'source'}; source is 'llm' or 'template'."""
    bn_text, en_text = template_texts(advice)
    result = {"bn": bn_text, "en": en_text, "source": "template"}
    if not (use_llm and GEMINI_API_KEY and _required_tokens(advice)):
        return result
    try:
        reply = _pool.submit(_ask_gemini, bn_text, advice).result(timeout=LLM_TIMEOUT_S)
        if validate(reply, advice):
            result.update(bn=reply, source="llm")
    except Exception as exc:  # network down, quota, timeout -> template stays
        log.info("Gemini explanation skipped: %s", type(exc).__name__)
    return result
