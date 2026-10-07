"""Call check: how well the assistants handled a call, with an overall score.

Most checks come from the app's own records (tool calls, the ticket, routed work), so they're
facts. One check, "avoided unsupported promises", is graded by ElevenLabs after the call against
a criterion set on the agent; it's labeled as AI-judged. Checks that don't apply to a call are
"not applicable" and don't count toward the score. Nothing is guessed: if something wasn't
recorded, the check says so.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

import requests

from app import analysis_spec, config, lifecycle
from app.store import get_store, now_iso

log = logging.getLogger("nightshift")

CRITERION = "no_unsupported_promises"
CONFIRMED = "confirmed_details_first"
CRITERIA = analysis_spec.CRITERIA_IDS  # every AI-judged check set on the agent
RECHECK_SECONDS = 20  # while ElevenLabs is still analyzing, ask at most this often per call
SPECIALIST_TOOLS = {"billing_lookup", "request_billing_review", "record_sales_interest"}

# Who an ElevenLabs agent id is, for the turn-by-turn trace
AGENT_NAMES = {
    config.ELEVENLABS_AGENT_ID: "Sam",
    config.FOLLOWUP_AGENT_ID: "Sam (check-in call)",
    "agent_4001m3zfgp9efne9gm350187zpfb": "Jordan",
    "agent_3001m3zg26pted8trz8p4pxt4qfc": "Riley",
}


def _ms(metrics: dict, key: str) -> int | None:
    value = (metrics.get(key) or {}).get("elapsed_time")
    return round(value * 1000) if isinstance(value, (int, float)) else None


def turn_trace(transcript: list[dict]) -> list[dict]:
    """ElevenLabs' own measurements, turn by turn. The caller's words are left out on purpose:
    this is a public page, so a caller turn shows only how long speech-to-text took."""
    rows = []
    for e in transcript[:80]:
        metrics = (e.get("conversation_turn_metrics") or {}).get("metrics") or {}
        at = e.get("time_in_call_secs")
        if e.get("role") == "user":
            words = len((e.get("message") or "").split())
            if not words:
                continue
            typed = e.get("source_medium") == "text"
            rows.append({"t": at, "who": "Caller", "kind": "typed" if typed else "spoke",
                         "text": f"{'Typed' if typed else 'Spoke'} ({words} word{'s' if words != 1 else ''})",
                         "stt_ms": None if typed else _ms(metrics, "convai_asr_trailing_service_latency")})
            continue
        who = AGENT_NAMES.get((e.get("agent_metadata") or {}).get("agent_id"), "Agent")
        for call in e.get("tool_calls") or []:
            rows.append({"t": at, "who": who, "kind": "tool", "text": f"Tool: {call.get('tool_name')}()",
                         "decide_ms": _ms(metrics, "convai_llm_tool_request_generation_latency")})
        for result in e.get("tool_results") or []:
            secs = result.get("tool_latency_secs")
            rows.append({"t": at, "who": who, "kind": "tool_result",
                         "text": f"Result: {result.get('tool_name')}" + (" (error)" if result.get("is_error") else ""),
                         "tool_ms": round(secs * 1000) if isinstance(secs, (int, float)) else None})
        if e.get("message"):
            rows.append({"t": at, "who": who, "kind": "reply", "text": e["message"][:180],
                         "first_word_ms": _ms(metrics, "convai_llm_service_ttfb"),
                         "voice_ms": _ms(metrics, "convai_tts_service_ttfb"),
                         "audio_after_silence_ms": _ms(metrics, "convai_ttf_audio_since_silence")})
    return rows


def call_metrics(data: dict) -> dict:
    """The numbers the Evaluation Lab scorecard needs from one ElevenLabs conversation record: its price,
    how fast the agent answered, how often the caller cut in, and how tool calls went. No words are kept."""
    meta = data.get("metadata") or {}
    answer_ms, agent_turns, interrupted, tools, tool_errors, transfers, transfer_errors = [], 0, 0, 0, 0, 0, 0
    for i, e in enumerate(data.get("transcript") or []):
        if e.get("role") != "agent":
            continue
        if e.get("message"):
            agent_turns += 1
            interrupted += bool(e.get("interrupted"))
            ms = _ms((e.get("conversation_turn_metrics") or {}).get("metrics") or {}, "convai_ttf_audio_since_silence")
            if ms is not None and i > 0:  # the greeting isn't an answer to anything
                answer_ms.append(ms)
        for result in e.get("tool_results") or []:
            is_transfer = result.get("tool_name") == "transfer_to_agent"
            transfers += is_transfer
            tools += not is_transfer
            if result.get("is_error"):
                transfer_errors += is_transfer
                tool_errors += not is_transfer
    cost = meta.get("cost_fiat")
    return {
        "cost_usd": round(cost, 5) if isinstance(cost, (int, float)) else None,
        "duration_s": meta.get("call_duration_secs"),
        "answer_ms": answer_ms[:60],
        "agent_turns": agent_turns,
        "interrupted": interrupted,
        "tool_calls": tools,
        "tool_errors": tool_errors,
        "transfers": transfers,
        "transfer_errors": transfer_errors,
    }


def fetch_grade(conversation_id: str | None, want_trace: bool = False, want_metrics: bool = False) -> dict:
    """ElevenLabs' post-call grades for this conversation, cached once final.
    Returns {"status": "done" | "pending" | "unavailable", "results": {criterion: {result, rationale}}, "summary"}."""
    if not conversation_id:
        return {"status": "unavailable"}
    store = get_store()
    try:
        cached = store.calls_by_ids([conversation_id]).get(conversation_id) or {}
    except Exception:  # noqa: BLE001
        cached = {}
    if cached.get("eval_status") == "done":
        saved = cached.get("evaluation") or {}
        if "results" in saved:
            if "trace" in saved and (not want_metrics or "metrics" in saved):
                return {"status": "done", "results": saved["results"], "trace": saved["trace"],
                        "metrics": saved.get("metrics"), "summary": cached.get("summary"),
                        "data": saved.get("data") or {}}
        else:  # saved before the trace was kept
            results = {CRITERION: saved} if "result" in saved else saved
            if not want_trace and not want_metrics:
                return {"status": "done", "results": results, "summary": cached.get("summary")}
    if not config.ELEVENLABS_API_KEY:
        return {"status": "unavailable"}
    last = cached.get("evaluated_at")
    if cached.get("eval_status") != "done" and last and \
            datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(seconds=RECHECK_SECONDS):
        return {"status": "pending"}
    try:
        res = requests.get(f"https://api.elevenlabs.io/v1/convai/conversations/{conversation_id}",
                           headers={"xi-api-key": config.ELEVENLABS_API_KEY}, timeout=6)
        if res.status_code != 200:
            raise RuntimeError(f"ElevenLabs answered {res.status_code}: {res.text[:300]}")
        data = res.json()
    except Exception:  # noqa: BLE001 - grading is a bonus; never break the page
        log.exception("Could not read the ElevenLabs analysis for %s", conversation_id)
        _remember(conversation_id, {"eval_status": "pending", "evaluated_at": now_iso()})
        return {"status": "pending"}
    if data.get("status") != "done":
        _remember(conversation_id, {"eval_status": "pending", "evaluated_at": now_iso()})
        return {"status": "pending"}
    found = analyze(data)
    _remember(conversation_id, record_fields(found))
    return {"status": "done", **{k: found[k] for k in ("results", "trace", "metrics", "summary", "data")}}


def analyze(data: dict) -> dict:
    """Everything NightAgent keeps from one finished ElevenLabs conversation, whether it came from the
    post-call webhook or from asking the API. Same shape both ways."""
    analysis = data.get("analysis") or {}
    graded = analysis.get("evaluation_criteria_results") or {}
    results = {c: {"result": (graded.get(c) or {}).get("result"),
                   "rationale": ((graded.get(c) or {}).get("rationale") or "")[:400]}
               for c in CRITERIA if c in graded}
    collected = analysis.get("data_collection_results") or {}
    fields = {}
    for key in analysis_spec.DATA_FIELDS:
        value = (collected.get(key) or {}).get("value")
        if value is not None and value != "":
            fields[key] = value
    meta = data.get("metadata") or {}
    return {
        "results": results,
        "trace": turn_trace(data.get("transcript") or []),
        "metrics": call_metrics(data),
        "data": fields,
        "summary": (analysis.get("transcript_summary") or "")[:500] or None,
        "call_successful": analysis.get("call_successful"),
        "duration_secs": meta.get("call_duration_secs"),
        "agent_id": data.get("agent_id"),
        "transcript": redact(transcript_text(data.get("transcript"))),
    }


def record_fields(found: dict) -> dict:
    """The ns_calls columns for an analyzed call."""
    return {
        "eval_status": "done",
        "evaluation": {k: found[k] for k in ("results", "trace", "metrics", "data")},
        "summary": found["summary"],
        "call_successful": found.get("call_successful"),
        "duration_secs": found.get("duration_secs"),
        "agent_id": found.get("agent_id"),
        "transcript": found.get("transcript"),
        "evaluated_at": now_iso(),
    }


def transcript_text(turns: list[dict] | None) -> str:
    lines = []
    for turn in turns or []:
        message = (turn.get("message") or "").strip()
        if not message:
            continue  # tool-call turns can have an empty message
        lines.append(f"{'Agent' if turn.get('role') == 'agent' else 'Caller'}: {message}")
    return "\n".join(lines)


_DIGIT_WORDS = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                "six": "6", "seven": "7", "eight": "8", "nine": "9"}
_TOKEN = r"\b(?:\d+|zero|oh|one|two|three|four|five|six|seven|eight|nine|double|triple)\b"
_TOKEN_RE = re.compile(_TOKEN, re.IGNORECASE)
# A run of digits and spoken digits ("310-555-0142", "three one oh, five five five, oh one four two")
_NUMBER_RUN = re.compile(rf"\(?{_TOKEN}(?:[\s,.()-]+{_TOKEN})*", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_DIGITS = 10  # runs this long are phone or account numbers; shorter ones (dates, counts, ticket numbers) stay


def _trim(m: re.Match) -> str:
    """Within one run, every stretch that adds up to 10 digits becomes •••last4; the rest is kept as said."""
    run, out, start, digits, repeat = m.group(0), "", 0, "", 1
    for tok in _TOKEN_RE.finditer(run):
        word = tok.group(0).lower()
        if word in ("double", "triple"):
            repeat = 2 if word == "double" else 3
            continue
        digits += (word if word.isdigit() else _DIGIT_WORDS[word]) * repeat
        repeat = 1
        if len(digits) >= PHONE_DIGITS:
            out += "•••" + digits[-4:]
            start, digits = tok.end(), ""
    return out + run[start:] if out else run


def redact(text: str | None) -> str | None:
    """Stored transcripts keep only the last four digits of any phone or account number, whether it was
    said as digits or read out as words, and no email addresses. Names and addresses on the fictional
    demo accounts stay; a real deployment would also redact those."""
    if not text:
        return None
    return _EMAIL.sub("[email]", _NUMBER_RUN.sub(_trim, text))


def _remember(conversation_id: str, fields: dict) -> None:
    try:
        get_store().merge_call(conversation_id, fields)
    except Exception:  # noqa: BLE001
        log.exception("Could not cache the analysis for %s", conversation_id)


def _item(label: str, status: str, detail: str, how: str = "rules") -> dict:
    return {"label": label, "status": status, "detail": detail, "how": how}


def _ai_item(label: str, grade: dict, criterion: str, passed_text: str, failed_text: str) -> dict:
    state = grade.get("status")
    found = (grade.get("results") or {}).get(criterion) or {}
    if state == "done" and found.get("result") in ("success", "failure"):
        ok = found["result"] == "success"
        return _item(label, "pass" if ok else "fail", found.get("rationale") or (passed_text if ok else failed_text), "ai")
    if state == "done":
        return _item(label, "na", "Not graded: the call was before this check existed, or nothing needed it", "ai")
    if state == "pending":
        return _item(label, "pending", "ElevenLabs is still reviewing the call", "ai")
    return _item(label, "na", "Not available for this call", "ai")


def _label(priority: str | None) -> str:
    return lifecycle.PRIORITY_LABELS.get(priority or "", priority or "not recorded").lower()


def build(kind: str, tool_calls: list[dict], grade: dict, ticket: dict | None = None,
          task: dict | None = None) -> dict | None:
    """kind: "ticket", "message", or "call" (handled on the call). None when there's nothing to check."""
    if not tool_calls:
        return None
    names = [t["tool"] for t in tool_calls]
    found = next((t for t in tool_calls if t["tool"] == "lookup_customer"
                  and (t.get("outcome") or "").startswith("Found")), None)
    specialist = bool(SPECIALIST_TOOLS & set(names))
    service = kind == "ticket" and ticket is not None
    items = []

    # 1. Who's calling
    if found:
        items.append(_item("Identified the customer", "pass", found["outcome"]))
    elif "lookup_customer" in names:
        items.append(_item("Identified the customer", "fail", "The account lookup found no match"))
    else:
        items.append(_item("Identified the customer", "fail", "The account was never looked up"))
    items.append(_ai_item("Confirmed name and number before acting", grade, CONFIRMED,
                          "Read back and confirmed before any ticket, message, or handoff",
                          "Acted before the caller confirmed their name and number"))

    # 2-4. Only service calls need a site, an emergency call, and a priority
    if service:
        has_site = bool(found or ticket.get("customer_id"))
        items.append(_item("Determined the location", "pass" if has_site else "fail",
                           "Site address on the customer's account" if has_site else "No account, so no site address"))
        suggested, final = ticket.get("suggested_priority"), ticket.get("priority")
        if not suggested:
            note = "The AI's suggestion wasn't recorded for this older call"
            items.append(_item("Identified emergency conditions", "na", note))
            items.append(_item("Set the correct ticket priority", "na", note))
        else:
            same_emergency = (suggested == "emergency") == (final == "emergency")
            items.append(_item("Identified emergency conditions", "pass" if same_emergency else "fail",
                               f"AI said {_label(suggested)}; our rules said {_label(final)}"))
            items.append(_item("Set the correct ticket priority", "pass" if suggested == final else "fail",
                               f"AI suggested {_label(suggested)}; final priority {_label(final)}"
                               + ("" if suggested == final else " (the rules corrected it)")))
    else:
        for label in ("Determined the location", "Identified emergency conditions", "Set the correct ticket priority"):
            items.append(_item(label, "na", "No repair ticket on this call"))

    # 5. Promises: graded by ElevenLabs from the transcript
    items.append(_ai_item("Avoided unsupported promises", grade, CRITERION,
                          "No unsupported promises", "Made a promise the tools didn't support"))

    # 6. Escalation: was it needed, and did it happen?
    dest = (task or {}).get("destination")
    if service and ticket.get("priority") == "emergency":
        alerted = any(t["tool"] == "page_on_call_tech" and "alerted" in (t.get("outcome") or "") for t in tool_calls)
        items.append(_item("Escalation needed", "info", "Yes: an emergency needs the on-call technician"))
        items.append(_item("Escalation performed", "pass" if alerted else "fail",
                           "On-call technician alerted" if alerted else "The on-call technician wasn't alerted"))
    elif specialist or dest in ("billing", "account_executive"):
        who = "Jordan, the billing assistant" if ({"billing_lookup", "request_billing_review"} & set(names)) or dest == "billing" \
            else "Riley, the sales assistant"
        items.append(_item("Escalation needed", "info", f"Yes: hand off to {who}"))
        items.append(_item("Escalation performed", "pass" if specialist else "fail",
                           f"Handed off to {who}" if specialist else "Took a message instead of handing off"))
    else:
        items.append(_item("Escalation needed", "info", "No"))
        items.append(_item("Escalation performed", "na", "Not needed on this call"))

    # 7. Follow-up
    if service:
        if ticket.get("resolution"):
            items.append(_item("Follow-up completed", "pass", "Check-in call done"))
        else:
            items.append(_item("Follow-up completed", "pending", "The check-in call comes after the repair"))
    elif task:
        who = (task.get("assigned_to") or "").replace(" (fictional)", "")
        when = task.get("best_time") or "next business day"
        items.append(_item("Follow-up completed", "pass", f"Callback booked with {who}, {when}"))
    else:
        items.append(_item("Follow-up completed", "na", "Nothing left to follow up: handled on the call"))

    passed = sum(1 for i in items if i["status"] == "pass")
    failed = sum(1 for i in items if i["status"] == "fail")
    pending = sum(1 for i in items if i["status"] == "pending")
    scored = passed + failed
    return {
        "score": round(100 * passed / scored) if scored else None,
        "passed": passed,
        "applicable": scored,
        "pending": pending,
        "items": items,
    }
