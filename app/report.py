"""The call report: what happened behind one ticket's conversation, in plain words.

Every line comes from records the app already keeps (the ticket, its history, the tool-call
log, routed tasks, and sales leads). Nothing is estimated: if something wasn't recorded, the
report says so instead of guessing.
"""
from app import lifecycle

TOOL_NAMES = {
    "lookup_customer": "Looked up the account",
    "create_ticket": "Created the ticket",
    "page_on_call_tech": "Alerted the on-call technician",
    "record_follow_up_outcome": "Saved the check-in result",
}

RESOLUTION_WORDS = {
    "resolved": "Customer said it's fixed",
    "problem_returned": "Customer said the problem came back",
    "never_fixed": "Customer said it was never really fixed",
    "unclear": "Outcome wasn't clear, so a person will call",
}

# The voices the demo page can pick (names only; the page holds the ElevenLabs ids).
VOICES = {"Lauren", "Sarah", "Matilda", "Eric", "Chris"}
TEXT_CHAT = "text"


TOOL_NAMES["take_message"] = "Took a message"


def _agent_and_channel(voice: str | None) -> tuple[str, str]:
    agent = "Sam, after-hours dispatcher" + (f" (voice: {voice})" if voice in VOICES else "")
    channel = "Text chat" if voice == TEXT_CHAT else "Voice call" if voice else "Live call"
    return agent, channel


def _tools_line(tool_calls: list[dict]) -> str:
    if not tool_calls:
        return "Not recorded"
    return f"{len(tool_calls)}: " + "; ".join(TOOL_NAMES.get(t["tool"], t["tool"]) for t in tool_calls)


def build_message(task: dict, tool_calls: list[dict], department: str, callback: str) -> dict:
    """The call report for a call that ended in a message, not a service ticket."""
    agent, channel = _agent_and_channel(task.get("voice"))
    rows = [
        {"label": "Agent", "value": agent},
        {"label": "Call", "value": channel},
        {"label": "What they needed", "value": task.get("summary") or "Not recorded"},
        {"label": "Asked for", "value": task.get("person_requested") or department},
        {"label": "Tools Sam used", "value": _tools_line(tool_calls)},
        {"label": "Service ticket", "value": "None: not a service problem"},
        {"label": "Handed to", "value": task.get("assigned_to") or "Not recorded"},
        {"label": "Callback", "value": f"{callback}, {task.get('best_time') or 'next business day'}"},
    ]
    return {"rows": rows, "tool_count": len(tool_calls)}


def public_tool_call(row: dict) -> dict:
    return {
        "tool": row["tool"],
        "label": TOOL_NAMES.get(row["tool"], row["tool"].replace("_", " ").capitalize()),
        "outcome": row.get("outcome") or "",
        "called_at": row.get("called_at"),
    }


def _customer_words(events: list[dict]) -> str | None:
    for e in events:
        text = e.get("description") or ""
        if e["event_type"] == "follow_up_completed" and text.startswith("Customer said: "):
            return text[len("Customer said: "):]
    return None


def build(ticket: dict, events: list[dict], tool_calls: list[dict], tasks: list[dict],
          opportunities: list[dict]) -> dict:
    tid = ticket["ticket_id"]
    priority = lifecycle.PRIORITY_LABELS.get(ticket.get("priority"), ticket.get("priority") or "")
    voice = ticket.get("voice")
    example = bool(ticket.get("scenario"))
    from_follow_up = bool(ticket.get("source_ticket_id"))

    if example:
        channel = "Example call (simulated: no real call took place)"
    elif from_follow_up:
        channel = f"Raised on NightAgent's check-in call for {ticket['source_ticket_id']}"
    elif voice == TEXT_CHAT:
        channel = "Text chat"
    elif voice:
        channel = "Voice call"
    else:
        channel = "Live call"

    agent = "Sam, after-hours dispatcher"
    if voice in VOICES:
        agent += f" (voice: {voice})"

    need = lifecycle.plain_words(ticket.get("priority_reason")).split(";")[0].strip() or "Not recorded"

    if ticket.get("paged_at"):
        escalated = "Yes: the on-call technician was alerted"
    elif ticket.get("priority") == "emergency":
        escalated = "High priority, sent straight to the service team"
    else:
        escalated = "No"

    if tool_calls:
        names = [TOOL_NAMES.get(t["tool"], t["tool"]) for t in tool_calls]
        tools = f"{len(tool_calls)}: " + "; ".join(names)
    elif example:
        tools = "None: this example skips the call"
    else:
        tools = "Not recorded (this call came before tool tracking started)"

    status = lifecycle.normalize_state(ticket.get("status"))
    resolution = ticket.get("resolution")
    if resolution:
        check_in = RESOLUTION_WORDS.get(resolution, resolution)
        if ticket.get("csat"):
            check_in += f", rated the visit {ticket['csat']} out of 5"
    elif status == "follow_up_pending":
        check_in = "Ready: NightAgent can call now"
    else:
        check_in = "Not yet: comes after the repair"

    owners = []
    for t in tasks:
        if t.get("assigned_to") and t["assigned_to"] not in owners:
            owners.append(t["assigned_to"])
    handoff = "; ".join(owners) if owners else ("No one needed" if resolution else "Not yet")

    opportunity = "; ".join(o.get("interest") or o.get("type") or "" for o in opportunities) or "None"

    rows = [
        {"label": "Agent", "value": agent},
        {"label": "Call", "value": channel},
        {"label": "What they needed", "value": need},
        {"label": "Priority", "value": f"{priority} (set by our rules, not the AI)"},
        {"label": "Escalated", "value": escalated},
        {"label": "Tools Sam used", "value": tools},
        {"label": "Ticket", "value": f"{tid} created"},
        {"label": "Check-in call", "value": check_in},
    ]
    words = _customer_words(events)
    if words:
        rows.append({"label": "Customer's words", "value": f"“{words}”"})
    rows += [
        {"label": "Handed to", "value": handoff},
        {"label": "New opportunity", "value": opportunity},
    ]
    return {"rows": rows, "tool_count": len(tool_calls)}
