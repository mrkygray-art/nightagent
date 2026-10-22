"""What the "NightAgent Call" Zendesk sidebar app shows for one Zendesk ticket that NightAgent made.

Read-only, from stored records only: nothing here calls ElevenLabs or Zendesk. The agent reading it is
staff, so the redacted transcript is included, but no full phone numbers, conversation ids, audio, or keys.
Free text (summary, check details, transcript) goes through evaluation.redact() again on the way out.
"""
import re

from app import evaluation, lifecycle

# turn_trace() writes tool results as "Result: <tool name>" with " (error)" when the tool failed.
_RESULT = re.compile(r"^Result: (?P<name>.+?)(?P<error> \(error\))?$")


def _grade(call: dict | None) -> dict:
    """The stored ElevenLabs grades, in fetch_grade()'s shape, without ever asking ElevenLabs."""
    if not call or call.get("eval_status") != "done":
        return {"status": "pending"}
    saved = call.get("evaluation") if isinstance(call.get("evaluation"), dict) else {}
    return {"status": "done", "results": saved.get("results") or {}}


def tool_calls(call: dict | None, logged: list[dict]) -> list[dict]:
    """Every tool call in order. ElevenLabs' trace knows whether each one failed; until it's stored, our own
    log is used, which only records calls that went through, so those are all ok."""
    trace = ((call or {}).get("evaluation") or {}).get("trace") if isinstance((call or {}).get("evaluation"), dict) else None
    if trace:
        out = []
        for row in trace:
            found = _RESULT.match(row.get("text") or "") if row.get("kind") == "tool_result" else None
            if found:
                out.append({"name": found["name"], "ok": not found["error"], "agent": row.get("who"),
                            "seconds_into_call": row.get("t"), "source": "elevenlabs"})
        return out
    return [{"name": r["tool"], "ok": True, "called_at": r.get("called_at"), "source": "nightagent_log"}
            for r in logged]


def _transcript(text: str | None) -> list[dict]:
    lines = []
    for line in (evaluation.redact(text) or "").splitlines():
        speaker, _, said = line.partition(": ")
        if said and speaker in ("Agent", "Caller"):
            lines.append({"speaker": speaker, "text": said})
    return lines


def build(ticket: dict, zendesk_id: int, call: dict | None, logged: list[dict]) -> dict:
    """logged: our tool-call log for this ticket's conversation, oldest first."""
    priority = ticket.get("priority")
    check = evaluation.build("ticket", logged, _grade(call), ticket=ticket)
    return {
        "zendesk_ticket_id": zendesk_id,
        "nightagent_ticket_id": ticket["ticket_id"],
        "caller_name": ticket.get("caller_name"),
        "priority": priority,
        "priority_label": lifecycle.PRIORITY_LABELS.get(priority, priority),
        "call_summary": evaluation.redact((call or {}).get("summary")),
        "analysis_status": "done" if (call or {}).get("eval_status") == "done" else "pending",
        "tool_calls": tool_calls(call, logged),
        "call_check": None if not check else {
            "score": check["score"], "passed": check["passed"], "applicable": check["applicable"],
            "checks": [{"label": i["label"], "status": i["status"], "detail": evaluation.redact(i["detail"]),
                        "judged_by": i["how"]} for i in check["items"]],
        },
        "transcript": _transcript((call or {}).get("transcript")),
    }
