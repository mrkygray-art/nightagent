"""Business Impact: every metric's one definition, counted from records NightAgent already keeps.

The unit is the contact: one inbound call (live) or one scripted scenario (synthetic). Each contact
gets exactly one primary outcome, so the outcome buckets always add up to contacts handled. Everything
else (ticket created, emergency rule fired, transferred, repeat contact) is a flag on top of that.

Live or synthetic is decided in one place, source_of_ticket(). A scripted scenario is a synthetic
customer, and so is anything that hangs off its ticket (the check-in call, tasks, leads). Voice-test
calls are neither: they are left out entirely.

Nothing here is estimated except after-call work saved, which the page labels Estimate and computes
from the two named assumptions below.
"""
from app import voice_lab
from app.routes_tools import DUPLICATE_HOURS

LIVE, SYNTHETIC, ALL = "live", "synthetic", "all"
VIEWS = (LIVE, SYNTHETIC, ALL)
DEFAULT_VIEW = LIVE

# After-call work (ACW) a person would otherwise do. Assumptions, shown on the page next to the number.
MINUTES_PER_INTAKE_CALL = 6  # answering, account lookup, triage, writing the ticket
MINUTES_PER_FOLLOW_UP = 5    # calling back, confirming the fix, logging the outcome

# A contact about a problem that already has an open ticket for the same site, within this window.
# Same constant the create_ticket tool uses to add the call to the open ticket instead of a new one.
REPEAT_CONTACT_WINDOW_HOURS = DUPLICATE_HOURS

# Primary outcomes, in precedence order: a call that does several things lands in the first that applies.
OUTCOMES = {
    "dispatched": "Dispatched: on-call technician paged",
    "deferred": "Deferred to the next business day",
    "transferred": "Transferred to a specialist",
    "message_taken": "Message taken",
    "resolved_on_call": "Resolved on the call",
}

# The caller's reason for calling, from ElevenLabs data collection (app/analysis_spec.py)
INTENT_LABELS = {
    "service_problem": "Something isn't working",
    "billing": "Billing",
    "sales": "Buying or upgrading",
    "message_for_person": "Wants a person or department",
    "how_to": "How-to question",
    "complaint": "Complaint",
    "off_topic": "Off-topic",
    "unclear": "Unclear",
}
TOP_REASONS = 4

SPECIALIST_TOOLS = {"billing_lookup", "request_billing_review", "record_sales_interest"}
FOLLOW_UP_TOOL = "record_follow_up_outcome"

DEFINITIONS = [
    ("Contacts handled", "Every inbound call Sam answered (live) plus every scripted scenario started (synthetic). "
     "A call counts once, however many tools it used. Voice-test calls are left out."),
    ("Top contact reasons", "Live contacts by the caller's main reason, as ElevenLabs classified it after the call "
     "(data collection on the agent). Calls from before this was switched on aren't classified; the subtitle says how "
     "many are. Scripted scenarios have no call, so they have no reason."),
    ("Outcome of each contact", "Each contact gets one primary outcome, the first that applies: dispatched (a ticket "
     "whose on-call technician was paged), deferred (a ticket for the next business day), transferred (handed to "
     "Jordan or Riley), message taken, or resolved on the call. A repeat call added to an open ticket takes that "
     "ticket's outcome. The five add up to contacts handled."),
    ("Containment rate", "Contacts resolved on the call (no ticket, no transfer, no message for a person) divided by "
     "contacts handled."),
    ("Messages taken", "Contacts whose outcome is a message for a department or person. Never counted as contained."),
    ("Emergencies escalated by rule", "Contacts whose ticket is emergency priority. The priority comes from the rules "
     "in code (app/triage.py); the AI can raise it but never lower it. Share is of contacts handled."),
    ("Warm transfers", "Contacts where Sam handed the caller to Jordan (billing) or Riley (sales) mid-call: a specialist "
     "tool ran, or ElevenLabs recorded a transfer. Transfer rate is that count divided by contacts handled. A transfer "
     "on a call that also made a ticket counts here but its outcome is the ticket's."),
    ("Supervisor escalations", "Work passed to the service manager: a caller asking for a manager, a low rating, or a "
     "check-in where the customer said it was never fixed."),
    ("After-hours dispatches", "Contacts whose outcome is dispatched. The subtitle counts contacts deferred to the next "
     "business day. Scripted scenarios never page anyone, so in Synthetic every ticket is deferred."),
    ("Proactive follow-up calls", "Check-in calls NightAgent made that recorded an outcome."),
    ("Customer-confirmed resolution", "Customers who said it's fixed on the check-in call, divided by check-in calls "
     "answered (calls that recorded an outcome)."),
    ("Repeat contacts", f"Contacts about a problem that already had an open ticket for the same site, within "
     f"{REPEAT_CONTACT_WINDOW_HOURS} hours, divided by contacts handled. Problems that came back after the repair "
     "(said on the check-in call) are shown beside it."),
    ("After-call work (ACW) saved", f"Estimate, live calls only: live contacts × {MINUTES_PER_INTAKE_CALL} min plus "
     f"live check-in calls × {MINUTES_PER_FOLLOW_UP} min. Both are assumptions, set in app/metrics.py."),
    ("Average handle time (AHT)", "Mean call length of live contacts, from the call duration ElevenLabs reports. Only "
     "calls with a stored duration are averaged; the subtitle says how many."),
    ("Service-to-sales opportunities", "Upgrade leads opened for the account executive. Value is never guessed."),
    ("Ticket creation rate", "Tickets created by contacts divided by contacts handled. Tickets raised later on a "
     "check-in call are shown beside it, not in the rate."),
    ("Follow-up tasks created", "Work routed to a person: messages, callbacks, return visits, and escalations."),
]


def source_of_ticket(ticket: dict | None, by_id: dict[str, dict]) -> str:
    """The one rule for live vs synthetic: a ticket is synthetic if it, or the ticket it was raised from,
    came from a scripted scenario."""
    seen = set()
    while ticket and ticket["ticket_id"] not in seen:
        if ticket.get("scenario"):
            return SYNTHETIC
        seen.add(ticket["ticket_id"])
        ticket = by_id.get(ticket.get("source_ticket_id") or "")
    return LIVE


def call_metric(call: dict | None, key: str):
    """One number from ElevenLabs' own record of the call, as cached by the call check."""
    call = call or {}
    evaluation = call.get("evaluation")
    m = call.get("metrics") or (evaluation.get("metrics") if isinstance(evaluation, dict) else None) or {}
    return m.get(key) if isinstance(m, dict) else None


def call_data(call: dict | None) -> dict:
    """Facts ElevenLabs pulled from the call (data collection), as cached by the webhook or the call check."""
    call = call or {}
    evaluation = call.get("evaluation")
    d = call.get("data") or (evaluation.get("data") if isinstance(evaluation, dict) else None)
    return d if isinstance(d, dict) else {}


def call_duration(call: dict | None) -> float | None:
    """Seconds, from the post-call webhook, or from ElevenLabs' own record cached by the call check."""
    for value in ((call or {}).get("duration_secs"), call_metric(call, "duration_s")):
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None


def outcome_for(tickets: list[dict], transferred: bool, message: bool) -> str:
    """Primary outcome, by the precedence in OUTCOMES."""
    if any(t.get("paged_at") for t in tickets):
        return "dispatched"
    if tickets:
        return "deferred"
    if transferred:
        return "transferred"
    if message:
        return "message_taken"
    return "resolved_on_call"


def contacts(rows: dict) -> list[dict]:
    """One dict per contact: source, outcome, and flags."""
    tickets = rows["tickets"]
    by_id = {t["ticket_id"]: t for t in tickets}
    calls = {c["conversation_id"]: c for c in rows["calls"]}

    tools_by_conv: dict[str, set[str]] = {}
    tickets_by_conv: dict[str, set[str]] = {}
    for r in rows["tool_calls"]:
        conv = r.get("conversation_id")
        if not conv:
            continue
        tools_by_conv.setdefault(conv, set()).add(r["tool"])
        if r.get("ticket_id"):
            tickets_by_conv.setdefault(conv, set()).add(r["ticket_id"])
    created_by_conv: dict[str, list[dict]] = {}
    repeat_convs = set()
    for t in tickets:
        if t.get("conversation_id") and not t.get("source_ticket_id"):
            created_by_conv.setdefault(t["conversation_id"], []).append(t)
            tickets_by_conv.setdefault(t["conversation_id"], set()).add(t["ticket_id"])
        for conv in t.get("repeat_conversation_ids") or []:
            repeat_convs.add(conv)
            tickets_by_conv.setdefault(conv, set()).add(t["ticket_id"])
    follow_up_convs = {t["follow_up_conversation_id"] for t in tickets if t.get("follow_up_conversation_id")}
    follow_up_convs |= {c for c, tools in tools_by_conv.items() if tools <= {FOLLOW_UP_TOOL}}
    tasks_by_conv: dict[str, list[dict]] = {}
    for k in rows["tasks"]:
        if k.get("source_conversation_id"):
            tasks_by_conv.setdefault(k["source_conversation_id"], []).append(k)

    out = []
    # Live: every front-desk conversation in the tool-call log, plus calls that made a ticket before the log existed
    convs = (set(tools_by_conv) | set(created_by_conv)) - follow_up_convs
    for conv in sorted(convs):
        if voice_lab.is_test(conv):
            continue
        own = [by_id[i] for i in sorted(tickets_by_conv.get(conv, ())) if i in by_id]
        own = [t for t in own if not t.get("source_ticket_id")]  # a check-in ticket isn't this call's
        transferred = bool(tools_by_conv.get(conv, set()) & SPECIALIST_TOOLS) or (call_metric(calls.get(conv), "transfers") or 0) > 0
        conv_tasks = tasks_by_conv.get(conv, [])
        message = any(not k.get("source_ticket_id") for k in conv_tasks)
        out.append({
            "source": LIVE,
            "key": conv,
            "outcome": outcome_for(own, transferred, message),
            "tickets_created": len(created_by_conv.get(conv, [])),
            "emergency": any(t.get("priority") == "emergency" for t in own),
            "transferred": transferred,
            "repeat": conv in repeat_convs,
            "duration": call_duration(calls.get(conv)),
            "intent": call_data(calls.get(conv)).get("intent"),
        })
    # Live tickets with no conversation id at all still came from a call
    for t in tickets:
        if not t.get("conversation_id") and not t.get("scenario") and not t.get("source_ticket_id"):
            out.append({"source": LIVE, "key": f"ticket:{t['ticket_id']}", "outcome": outcome_for([t], False, False),
                        "tickets_created": 1, "emergency": t.get("priority") == "emergency",
                        "transferred": False, "repeat": False, "duration": None, "intent": None})
    # Synthetic: one contact per scripted scenario
    for t in tickets:
        if t.get("scenario") and not t.get("source_ticket_id"):
            out.append({"source": SYNTHETIC, "key": f"scenario:{t['ticket_id']}", "outcome": outcome_for([t], False, False),
                        "tickets_created": 1, "emergency": t.get("priority") == "emergency",
                        "transferred": False, "repeat": False, "duration": None, "intent": None})
    return out


def _pct(n: int, d: int) -> int | None:
    return round(100 * n / d) if d else None


def _in_view(source: str, view: str) -> bool:
    return view == ALL or source == view


def view_metrics(rows: dict, view: str, people: list[dict] | None = None) -> dict:
    """Every tile's number for one view (live, synthetic, or all)."""
    by_id = {t["ticket_id"]: t for t in rows["tickets"]}
    tests = voice_lab.is_test

    def ticket_src(ticket_id):
        return source_of_ticket(by_id.get(ticket_id or ""), by_id) if ticket_id in by_id else LIVE

    def record_src(r):  # tasks and leads: their ticket's source, else the call's (always live)
        return ticket_src(r["source_ticket_id"]) if r.get("source_ticket_id") else LIVE

    def real(r):
        return r.get("source_ticket_id") or not tests(r.get("source_conversation_id"))

    cs = [c for c in (people if people is not None else contacts(rows)) if _in_view(c["source"], view)]
    n = len(cs)
    outcomes = {k: sum(1 for c in cs if c["outcome"] == k) for k in OUTCOMES}
    events = [e for e in rows["events"] if _in_view(ticket_src(e["ticket_id"]), view)]

    def count(kind):
        return sum(1 for e in events if e["event_type"] == kind)

    tasks = [k for k in rows["tasks"] if real(k) and _in_view(record_src(k), view)]
    opps = [o for o in rows["opportunities"] if real(o) and _in_view(record_src(o), view)]
    created = sum(c["tickets_created"] for c in cs)
    from_check_in = sum(1 for t in rows["tickets"] if t.get("source_ticket_id") and _in_view(ticket_src(t["ticket_id"]), view))
    emergencies = sum(1 for c in cs if c["emergency"])
    transfers = sum(1 for c in cs if c["transferred"])
    repeats = sum(1 for c in cs if c["repeat"])
    check_ins, confirmed = count("follow_up_completed"), count("resolution_confirmed")
    reasons: dict[str, int] = {}
    for c in cs:
        if c.get("intent") in INTENT_LABELS:
            reasons[c["intent"]] = reasons.get(c["intent"], 0) + 1
    top = sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_REASONS]
    return {
        "top_reasons": [{"intent": k, "label": INTENT_LABELS[k], "count": n} for k, n in top],
        "classified": sum(reasons.values()),
        "contacts": n,
        "live": sum(1 for c in cs if c["source"] == LIVE),
        "synthetic": sum(1 for c in cs if c["source"] == SYNTHETIC),
        "outcomes": outcomes,
        "contained": outcomes["resolved_on_call"],
        "containment_rate": _pct(outcomes["resolved_on_call"], n),
        "messages_taken": outcomes["message_taken"],
        "emergencies": emergencies,
        "emergency_share": _pct(emergencies, n),
        "transfers": transfers,
        "transfer_rate": _pct(transfers, n),
        "supervisor_escalations": sum(1 for k in tasks if k.get("destination") == "service_manager"),
        "dispatches": outcomes["dispatched"],
        "deferred": outcomes["deferred"],
        "follow_up_calls": check_ins,
        "confirmed_resolved": confirmed,
        "check_ins_answered": check_ins,
        "confirmed_rate": _pct(confirmed, check_ins),
        "repeat_contacts": repeats,
        "repeat_rate": _pct(repeats, n),
        "came_back": count("ticket_reopened"),
        "opportunities": len(opps),
        "tickets_created": created,
        "ticket_rate": _pct(created, n),
        "tickets_from_check_ins": from_check_in,
        "follow_up_tasks": len(tasks),
    }


def live_only(rows: dict, people: list[dict]) -> dict:
    """After-call work and handle time: live calls by definition, whatever view is picked."""
    live = [c for c in people if c["source"] == LIVE]
    by_id = {t["ticket_id"]: t for t in rows["tickets"]}
    live_check_ins = sum(1 for e in rows["events"] if e["event_type"] == "follow_up_completed"
                         and source_of_ticket(by_id.get(e["ticket_id"]), by_id) == LIVE)
    timed = [c["duration"] for c in live if c["duration"]]
    return {
        "acw_minutes": len(live) * MINUTES_PER_INTAKE_CALL + live_check_ins * MINUTES_PER_FOLLOW_UP,
        "live_contacts": len(live),
        "live_check_ins": live_check_ins,
        "aht_seconds": round(sum(timed) / len(timed)) if timed else None,
        "aht_timed": len(timed),
        "aht_calls": len(live),
    }


def impact(rows: dict) -> dict:
    people = contacts(rows)
    return {
        "default_view": DEFAULT_VIEW,
        "views": {v: view_metrics(rows, v, people) for v in VIEWS},
        "live_only": live_only(rows, people),
        "synthetic_scenarios": sum(1 for c in people if c["source"] == SYNTHETIC),
        "outcome_labels": OUTCOMES,
        "assumptions": {
            "minutes_per_intake_call": MINUTES_PER_INTAKE_CALL,
            "minutes_per_follow_up": MINUTES_PER_FOLLOW_UP,
            "repeat_contact_window_hours": REPEAT_CONTACT_WINDOW_HOURS,
        },
        "definitions": [{"label": a, "how": b} for a, b in DEFINITIONS],
    }
