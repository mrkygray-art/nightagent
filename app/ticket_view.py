"""The ticket view's handoff sections: what the next person needs to pick up the call without asking
the caller again.

Every field comes from a stored record. When something isn't stored, the field says so ("not_captured")
or is left out; nothing is written after the fact. Live callers' words (transcripts) never leave the
server; a synthetic scenario's transcript may.
"""
from app import lifecycle, metrics
from app.report import RESOLUTION_WORDS, SPECIALISTS
from app.service import mask_phone
from app.triage import CATEGORY_POLICY

# The five things a person picking up a dispatched or transferred ticket should be handed.
HANDOFF_ITEMS = {
    "summary": "AI summary",
    "transcript": "Transcript",
    "account": "Account record",
    "actions": "Actions taken",
    "identity": "Identity check",
}

# What the dispatcher should do next, by the ticket's state. Plain rules, not AI.
NEXT_STEP = {
    "new": "Confirm the details and queue the ticket",
    "awaiting_dispatch": "Assign a technician when the office opens",
    "dispatched": "Confirm the on-call technician called the customer back",
    "technician_assigned": "Technician to head to the site",
    "en_route": "Technician arriving on site",
    "onsite": "Technician working on the repair",
    "work_completed": "Check-in call with the customer",
    "follow_up_pending": "Check-in call with the customer",
    "reopened": "Schedule a return visit",
    "escalated": "Service manager to call the customer",
}


def handoff_context(*, summary: bool, transcript: bool, account: bool, actions: bool, identity: bool) -> dict:
    """How many of the five handoff items exist on this ticket. Reused by Step 2's scorecard."""
    have = {"summary": summary, "transcript": transcript, "account": account, "actions": actions, "identity": identity}
    return {"items": [{"key": k, "label": HANDOFF_ITEMS[k], "present": bool(have[k])} for k in HANDOFF_ITEMS],
            "count": sum(1 for v in have.values() if v), "total": len(HANDOFF_ITEMS)}


def _account(customer: dict | None) -> dict | None:
    if not customer:
        return None
    return {
        "customer_id": customer["customer_id"],
        "business_name": customer.get("business_name"),
        "contact_name": customer.get("contact_name"),
        "phone": mask_phone(customer.get("phone_digits")),
        "site_address": customer.get("site_address"),
        "systems": customer.get("systems"),
        "service_plan": customer.get("service_plan"),
        "after_hours_coverage": bool(customer.get("after_hours_coverage")),
    }


def build(ticket: dict, *, source: str, call: dict | None, customer: dict | None, own_tool_calls: list[dict],
          tasks: list[dict], events: list[dict]) -> dict:
    """The sections for one ticket. `own_tool_calls` are the calls made on this ticket's own conversation."""
    conv = ticket.get("conversation_id")
    tools = {t["tool"] for t in own_tool_calls}
    transferred = bool(tools & metrics.SPECIALIST_TOOLS) or (metrics.call_metric(call, "transfers") or 0) > 0
    outcome = metrics.outcome_for([ticket], transferred, False)
    synthetic = source == metrics.SYNTHETIC
    status = lifecycle.normalize_state(ticket.get("status"))

    summary = (call or {}).get("summary")
    transcript = (call or {}).get("transcript") or None
    account = _account(customer)

    escalation = []
    if ticket.get("priority") == "emergency":
        escalation.append({"kind": "emergency_rule", "label": "Emergency rule",
                           "detail": "Our rules set high priority; " + ("the on-call technician was paged" if ticket.get("paged_at")
                                     else "no technician was paged" + (" (scripted scenario)" if source == metrics.SYNTHETIC else ""))})
    from_call = [k for k in tasks if conv and k.get("source_conversation_id") == conv]
    for k in from_call:
        if k.get("destination") == "service_manager":
            escalation.append({"kind": "asked_for_person", "label": "Caller asked for a person",
                               "detail": k.get("assigned_to") or "Service manager"})
        elif k.get("destination") == "billing":
            escalation.append({"kind": "needs_authority", "label": "Needs authority",
                               "detail": f"Billing review: {k.get('assigned_to')}"})
    specialists = []
    for t in own_tool_calls:
        who = SPECIALISTS.get(t["tool"])
        if who and who not in specialists:
            specialists.append(who)

    category = ticket.get("category")
    intent = CATEGORY_POLICY[category][1] if category in CATEGORY_POLICY else None

    resolution = ticket.get("resolution")
    check_in = None
    if resolution:
        words = next((e.get("description", "")[len("Customer said: "):] for e in events
                      if e["event_type"] == "follow_up_completed" and (e.get("description") or "").startswith("Customer said: ")), None)
        check_in = {"result": RESOLUTION_WORDS.get(resolution, resolution),
                    "csat": ticket.get("csat"),
                    # A scripted scenario's check-in words may be shown; a live customer's stay private
                    "words": words if synthetic else None}
    repeat_calls = sum(1 for e in events if e["event_type"] == "caller_called_again")

    no_call = synthetic and not conv
    return {
        "source": source,
        "outcome": outcome,
        "outcome_label": metrics.OUTCOMES[outcome],
        "transferred": transferred,
        "summary": {"text": summary, "open": lifecycle.STATE_LABELS[status],
                    "status": "ok" if summary else "no_call" if no_call else "pending"},
        "intent": {"problem_type": intent, "escalation": escalation, "specialists": specialists,
                   "next_step": NEXT_STEP.get(status)},
        "actions_status": "ok" if own_tool_calls else "no_call" if no_call else "not_captured",
        "identity": {"status": "not_captured"},
        "account": account,
        "whisper": {"status": "not_captured"} if transferred else None,
        "follow_up": {"check_in": check_in, "original_ticket": ticket.get("source_ticket_id"),
                      "repeat_calls": repeat_calls},
        # Live callers' words never reach a public page
        "transcript": transcript if synthetic else None,
        "handoff": handoff_context(summary=bool(summary), transcript=bool(transcript), account=bool(account),
                                   actions=bool(own_tool_calls), identity=False)
                   if outcome == "dispatched" or transferred else None,
    }
