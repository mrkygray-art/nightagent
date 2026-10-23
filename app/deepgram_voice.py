"""Sam on Deepgram: the same front desk on the Deepgram Voice Agent API (Flux listens, Aura-2 speaks, Claude thinks).

The browser opens the agent WebSocket straight to Deepgram with a short-lived token from /api/deepgram/session,
so no audio passes through this server. Sam's functions are client-side: Deepgram sends a FunctionCallRequest to
the browser, which posts it to /api/deepgram/tool with the signed session, and the same tool code ElevenLabs Sam
uses runs here. When the call ends, the browser posts the transcript to /api/deepgram/end, which stores it,
asks Deepgram's Text Intelligence for a summary and sentiment, and logs the call in Zendesk.

Deepgram calls have conversation ids starting with "dg_", which is how the board and Zendesk tell them apart."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from pathlib import Path

import requests

from app import config

log = logging.getLogger("nightshift")

PREFIX = "dg_"
AGENT_ID = "deepgram-sam"
AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"
SESSION_MINUTES = 15  # a signed session works this long; the page hangs up well before (MAX_CALL_SECONDS)
MAX_CALL_SECONDS = 6 * 60
MAX_TOOL_CALLS = 30  # per call; Sam needs fewer than ten on a busy one
TIMEOUT_SECS = 10

PROMPT = Path(__file__).with_name("deepgram_sam_prompt.md")
FUNCTIONS = Path(__file__).with_name("deepgram_functions.json")
GREETING = "Thanks for calling Demo Security Integrators after-hours support, this is Sam. How can I help you tonight?"
# Words Flux should expect: the demo accounts and the trade's terms
KEYTERMS = ["Demo Security Integrators", "Sunset Dental", "Westside Self Storage", "Harbor Logistics",
            "keypad", "fob", "access control", "intercom", "NVR"]


def is_deepgram(conversation_id: str | None) -> bool:
    return bool(conversation_id) and conversation_id.startswith(PREFIX)


def configured() -> bool:
    return bool(config.DEEPGRAM_API_KEY)


def settings() -> dict:
    """The Settings message the browser sends right after the socket opens."""
    return {
        "type": "Settings",
        "tags": ["nightagent"],
        "audio": {"input": {"encoding": "linear16", "sample_rate": 16000},
                  "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"}},
        "agent": {
            "listen": {"provider": {"type": "deepgram", "version": "v2", "model": "flux-general-en",
                                    "keyterms": KEYTERMS}},
            "think": {"provider": {"type": "anthropic", "model": config.DEEPGRAM_LLM, "temperature": 0.3},
                      "prompt": PROMPT.read_text(encoding="utf-8"),
                      "functions": json.loads(FUNCTIONS.read_text(encoding="utf-8"))},
            "speak": {"provider": {"type": "deepgram", "version": "v1", "model": config.DEEPGRAM_VOICE}},
            "greeting": GREETING,
        },
    }


def grant_token() -> str:
    """A 30-second token for opening one agent socket (the socket stays open after it expires).
    The API key needs Member permissions to grant tokens."""
    r = requests.post("https://api.deepgram.com/v1/auth/grant", json={"ttl_seconds": 30},
                      headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"}, timeout=TIMEOUT_SECS)
    r.raise_for_status()
    return r.json()["access_token"]


# Signed sessions: proof that the tool and end-of-call requests come from a call this server started

def _key() -> bytes:
    secret = config.DEEPGRAM_SESSION_SECRET or config.TOOL_SECRET or "local-dev"
    return hashlib.sha256(f"deepgram-session:{secret}".encode()).digest()


def new_session(now: float | None = None) -> tuple[str, str]:
    """(conversation_id, signed session)"""
    conv = PREFIX + secrets.token_hex(12)
    expires = int((now or time.time()) + SESSION_MINUTES * 60)
    body = f"{conv}.{expires}"
    sig = base64.urlsafe_b64encode(hmac.new(_key(), body.encode(), hashlib.sha256).digest()).decode().rstrip("=")
    return conv, f"{body}.{sig}"


def check_session(session: str | None, now: float | None = None) -> str | None:
    """The conversation id, or None if the session is forged or expired."""
    try:
        conv, expires, sig = (session or "").split(".")
    except ValueError:
        return None
    want = base64.urlsafe_b64encode(hmac.new(_key(), f"{conv}.{expires}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    if not hmac.compare_digest(sig, want) or not is_deepgram(conv):
        return None
    if not expires.isdigit() or int(expires) < (now or time.time()):
        return None
    return conv


# Text Intelligence on the finished transcript: the summary for Zendesk and the caller's sentiment for review

def read_transcript(text: str) -> dict:
    """{"summary", "sentiment"}; empty if Deepgram is unreachable, so the call is still logged."""
    if not text or not configured():
        return {}
    try:
        r = requests.post("https://api.deepgram.com/v1/read", params={"summarize": "true", "sentiment": "true", "language": "en"},
                          json={"text": text[:20_000]}, headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"},
                          timeout=TIMEOUT_SECS)
        r.raise_for_status()
        results = r.json().get("results") or {}
    except Exception:  # noqa: BLE001
        log.exception("Deepgram Text Intelligence failed")
        return {}
    average = (results.get("sentiments") or {}).get("average") or {}
    # Review only counts clearly unhappy callers (review.SETTINGS["negative_sentiments"])
    negative = average.get("sentiment") == "negative" and (average.get("sentiment_score") or 0) <= -0.33
    return {"summary": ((results.get("summary") or {}).get("text") or "")[:500] or None,
            "sentiment": "frustrated" if negative else average.get("sentiment")}


def transcript_text(turns: list[dict]) -> str:
    lines = []
    for turn in turns[:400]:
        content = " ".join(str(turn.get("content") or "").split())[:1000]
        if content:
            lines.append(f"{'Agent' if turn.get('role') == 'assistant' else 'Caller'}: {content}")
    return "\n".join(lines)


def latency_summary(samples: list[dict]) -> dict | None:
    """Median and worst of Deepgram's AgentStartedSpeaking latencies (seconds) over the call."""
    def stats(key: str) -> dict | None:
        values = sorted(float(s[key]) for s in samples[:200] if isinstance(s.get(key), (int, float)) and 0 <= s[key] < 60)
        if not values:
            return None
        return {"median": round(values[len(values) // 2], 3), "max": round(values[-1], 3), "n": len(values)}
    out = {k: v for k in ("total_latency", "ttt_latency", "tts_latency") if (v := stats(k))}
    return out or None
