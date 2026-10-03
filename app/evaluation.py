"""Call check: how well the assistants handled a call, with an overall score.

Most checks come from the app's own records (tool calls, the ticket, routed work), so they're
facts. One check, "avoided unsupported promises", is graded by ElevenLabs after the call against
a criterion set on the agent; it's labeled as AI-judged. Checks that don't apply to a call are
"not applicable" and don't count toward the score. Nothing is guessed: if something wasn't
recorded, the check says so.
"""
import logging
from datetime import datetime, timedelta, timezone

import requests

from app import config, lifecycle
from app.store import get_store, now_iso

log = logging.getLogger("nightshift")

CRITERION = "no_unsupported_promises"
CONFIRMED = "confirmed_details_first"
CRITERIA = (CRITERION, CONFIRMED)
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
                        "metrics": saved.get("metrics"), "summary": cached.get("summary")}
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
    analysis = data.get("analysis") or {}
    if data.get("status") != "done":
        _remember(conversation_id, {"eval_status": "pending", "evaluated_at": now_iso()})
        return {"status": "pending"}
    graded = analysis.get("evaluation_criteria_results") or {}
    results = {c: {"result": (graded.get(c) or {}).get("result"),
                   "rationale": ((graded.get(c) or {}).get("rationale") or "")[:400]}
               for c in CRITERIA if c in graded}
    summary = (analysis.get("transcript_summary") or "")[:500] or None
    trace = turn_trace(data.get("transcript") or [])
    metrics = call_metrics(data)
    _remember(conversation_id, {"eval_status": "done", "evaluation": {"results": results, "trace": trace, "metrics": metrics},
                                "summary": summary, "evaluated_at": now_iso()})
    return {"status": "done", "results": results, "trace": trace, "metrics": metrics, "summary": summary}


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
