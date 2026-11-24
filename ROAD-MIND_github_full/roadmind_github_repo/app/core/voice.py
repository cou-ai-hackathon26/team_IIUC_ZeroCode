"""Bangla voice for the advice, made on the server so it plays in any browser (Chrome too).

Uses the free online neural voices through the `edge-tts` package (needs internet). Each sentence
is made once and kept in data/voice/. If there is no internet, the dashboard falls back to the
browser's own voice. Roadmind works fully without this.
"""
from __future__ import annotations

import asyncio
import hashlib
import os

from app.config import DATA_DIR

VOICE_DIR = DATA_DIR / "voice"
VOICES = {"bn": os.getenv("ROADMIND_VOICE_BN", "bn-BD-NabanitaNeural"),
          "en": os.getenv("ROADMIND_VOICE_EN", "en-US-AriaNeural")}


async def speech_mp3(text: str, lang: str = "bn") -> bytes | None:
    """MP3 bytes of the sentence, or None when the voice service cannot be reached."""
    text = (text or "").strip()[:400]
    if not text:
        return None
    voice = VOICES.get(lang, VOICES["bn"])
    key = hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:20]
    path = VOICE_DIR / f"{key}.mp3"
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes()
    try:
        import edge_tts  # optional: only needed for the server voice
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        await asyncio.wait_for(edge_tts.Communicate(text, voice, rate="-5%", volume="+0%").save(str(tmp)), 15)
        if tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(path)
            return path.read_bytes()
        tmp.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001 - no internet, package missing, service changed: use the browser voice
        return None
    return None
