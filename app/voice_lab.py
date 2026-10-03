"""Evaluation Lab: voice tests. Real audio, sent to the live Sam by voicelab/run.js the way a caller's
microphone would send it, and saved to voice_lab.json (scripts/save_voice_lab.py).

Three things are measured from those calls:
- whether a phone number and name come through exactly, in quiet and in noise and over a phone line;
- whether Sam stops when talked over and uses what the caller said, and what Sam does when a caller goes quiet;
- how long the caller waits: from the end of their speech to the first sound of Sam's reply, timed by the
  test caller itself.

These calls are tests, so their conversation ids are left out of the real-call numbers everywhere
(scorecard, calls list, Business Impact). The ids themselves never leave the server.
"""
from __future__ import annotations

import json
import re
import statistics
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name("voice_lab.json")

CONDITIONS = {  # mirrors voicelab/audio.js, mildest first
    "clean": "Quiet room",
    "cafe-10": "Busy café (10 dB)",
    "street-5": "Street traffic (5 dB)",
    "phone": "Phone line (8 kHz)",
    "phone-cafe-10": "Phone line + café (10 dB)",
    "cafe-0": "Loud café (0 dB)",
}


@lru_cache(maxsize=1)
def _load() -> dict:
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def test_conversation_ids() -> frozenset[str]:
    data = _load()
    ids = {r.get("conversation_id") for r in data.get("results") or []}
    ids.update(data.get("other_test_conversations") or [])
    return frozenset(i for i in ids if i)


def is_test(conversation_id: str | None) -> bool:
    return bool(conversation_id) and conversation_id in test_conversation_ids()


def _clean(text):
    if isinstance(text, list):
        return [_clean(t) for t in text]
    if isinstance(text, dict):
        return {k: _clean(v) for k, v in text.items()}
    if isinstance(text, str):
        return re.sub(r"\s+", " ", re.sub(r"\[[a-z][a-z ]{1,24}\]\s*", "", text)).strip()
    return text


def _typical(values: list[int]) -> dict:
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return {"n": 0, "typical_ms": None, "slow_ms": None}
    ordered = sorted(values)
    return {"n": len(values), "typical_ms": round(statistics.median(values)),
            "slow_ms": round(ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))])}


def summary(data: dict | None = None) -> dict:
    """What the /lab page shows. No conversation ids."""
    data = data if data is not None else _load()
    results = data.get("results") or []
    if not results:
        return {"status": "none"}
    numbers = [r for r in results if r.get("test") == "numbers"]
    rows = []
    for cid, label in CONDITIONS.items():
        calls = [r for r in numbers if r.get("condition") == cid]
        if not calls:
            continue
        rows.append({
            "condition": label, "calls": len(calls),
            "number_heard": sum(1 for r in calls if r.get("number_heard")),
            "name_heard": sum(1 for r in calls if r.get("name_heard")),
            "read_back_right": sum(1 for r in calls if r.get("read_back_right")),
            "response": _typical([r.get("response_ms") for r in calls]),
            # The caller paused after the number and Sam's turn began before they had finished
            "started_early": sum(1 for r in calls if r.get("started_before_caller_finished")),
            "turn_split": sum(1 for r in calls if r.get("turn_split")),
            # Anything short of a clean pass, with what was heard and what Sam said first
            "misses": [{"heard": r.get("heard"), "caller": r.get("caller"), "reply": (r.get("replies") or [""])[0]}
                       for r in calls
                       if not (r.get("number_heard") and r.get("name_heard") and r.get("read_back_right"))][:3],
        })

    def turn(runs: list[dict], key_ms: str) -> dict:
        passed = [r for r in runs if r.get("passed")]
        example = (passed or runs or [{}])[0]
        return {"runs": len(runs), "passed": len(passed), "timing": _typical([r.get(key_ms) for r in runs]),
                "example": {k: example.get(k) for k in ("read_back", "heard", "reply", "spoke_during_silence")
                            if example.get(k)},
                "failures": [{k: r.get(k) for k in ("reply", "spoke_during_silence", "hung_up", "stopped",
                                                      "talking_when_cut_in", "used_new_detail", "carried_on")}
                             for r in runs if not r.get("passed")][:2]}

    interruption = [r for r in results if r.get("test") == "interruption"]
    silence = [r for r in results if r.get("test") == "silence"]
    clean = [r.get("response_ms") for r in numbers if r.get("condition") == "clean"]
    noisy = [r.get("response_ms") for r in numbers if r.get("condition") != "clean"]
    return {
        "status": "ok",
        "run_at": data.get("run_at"),
        "voices": data.get("voices") or [],
        "numbers": _clean(rows),
        "interruption": _clean(turn(interruption, "stop_ms")),
        "silence": _clean({**turn(silence, "check_in_ms"),
                           "first_reply": _typical([r.get("first_reply_ms") for r in silence])}),
        "response_time": {
            "all": _typical(clean + noisy + [r.get("response_ms") for r in interruption]),
            "quiet": _typical(clean),
            "noisy": _typical(noisy),
        },
    }
