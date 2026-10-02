"""What happens after NightAgent's follow-up call.

The AI's job on the call is to listen and fill in a structured report (record_follow_up_outcome).
Everything that report causes is decided here, in code: which state the ticket moves to,
whether the priority is re-evaluated, who gets a task, and whether a sales lead is opened.
Nothing is invented: a lead's value is what the customer said, or TBD.
"""
from app import demo, lifecycle
from app.service import move_ticket, record_event
from app.store import get_store
from app.triage import triage

RESOLUTIONS = {"resolved", "problem_returned", "never_fixed", "unclear"}

# Who each kind of routed work goes to. Fictional people, labeled as such on the page.
DESTINATIONS = {
    "service": "Service desk",
    "service_manager": "Alex Moreno, Service Manager (fictional)",
    "account_executive": "Sarah Johnson, Account Executive (fictional)",
    "support": "Support desk",
}

VALUE_TBD = "TBD - AE qualification required"


def _clean(text: str | None, limit: int = 400) -> str:
    return " ".join((text or "").split())[:limit]


def _task(ticket: dict, customer: dict | None, destination: str, reason: str, summary: str,
          priority: str, conversation_id: str | None, requested: str | None = None) -> dict:
    if destination not in DESTINATIONS:
        destination = "service"  # only known teams can receive work
    task = get_store().create_task({
        "destination": destination,
        "assigned_to": DESTINATIONS[destination],
        "customer_id": ticket.get("customer_id"),
        "contact_name": ticket.get("caller_name"),
        "site_address": (customer or {}).get("site_address"),
        "source_ticket_id": ticket["ticket_id"],
        "source_conversation_id": conversation_id,
        "reason": reason,
        "summary": summary,
        "priority": priority,
        "requested_follow_up": requested,
        "demo": bool(ticket.get("demo")),
    })
    record_event(ticket["ticket_id"], "task_created",
                 f"{task['task_id']} for {DESTINATIONS[destination]}: {reason}",
                 source="follow_up", conversation_id=conversation_id, actor_type="system",
                 metadata={"task_id": task["task_id"], "destination": destination})
    return task


def apply_outcome(ticket: dict, report: dict, conversation_id: str | None) -> dict:
    """Apply a follow-up report to a ticket in follow_up_pending. Returns what was done, in
    plain sentences for the agent to tell the customer, plus the records created."""
    store = get_store()
    tid = ticket["ticket_id"]
    customer = store.get_customer(ticket["customer_id"]) if ticket.get("customer_id") else None
    resolution = report.get("resolution") if report.get("resolution") in RESOLUTIONS else "unclear"
    comments = _clean(report.get("customer_comments"))
    csat = report.get("satisfaction")
    csat = csat if isinstance(csat, int) and 1 <= csat <= 5 else None
    said, done = [], {"tasks": [], "opportunities": [], "tickets": []}
    common = {"source": "follow_up", "conversation_id": conversation_id}

    fields = {"follow_up_token_hash": None, "follow_up_conversation_id": conversation_id,
              "resolution": resolution}
    if csat:
        fields["csat"] = csat
    store.update_ticket(tid, fields)
    ticket = {**ticket, **fields}

    record_event(tid, "follow_up_completed",
                 f"Customer said: {comments}" if comments else "Follow-up call completed",
                 actor_type="customer", **common)
    if csat:
        record_event(tid, "csat_recorded", f"Satisfaction {csat} out of 5", actor_type="customer", **common)

    if resolution == "resolved":
        ticket = move_ticket(ticket, "resolved")
        record_event(tid, "resolution_confirmed", "Customer confirmed the original problem is fixed",
                     actor_type="customer", **common)
        ticket = move_ticket(ticket, "closed")
        record_event(tid, "ticket_closed", f"{tid} closed as resolved", actor_type="system", **common)
        said.append("The ticket is closed as resolved.")
        if csat and csat <= 2:
            done["tasks"].append(_task(ticket, customer, "service_manager", "Low satisfaction after a completed repair",
                                       comments or f"Customer rated the visit {csat} out of 5.", "high",
                                       conversation_id, "Call the customer to recover the relationship"))
            said.append("Because the visit didn't go well, the service manager will call you.")

    elif resolution == "problem_returned":
        ticket = move_ticket(ticket, "reopened")
        record_event(tid, "ticket_reopened", "Customer reported the original problem came back",
                     actor_type="customer", **common)
        # Re-check the priority from the impact right now, not the old ticket's priority.
        category, priority, reason = triage(report.get("current_category") or ticket.get("category"),
                                            report.get("suggested_priority"))
        store.update_ticket(tid, {"priority": priority, "priority_reason": reason, "category": category})
        ticket = {**ticket, "priority": priority, "priority_reason": reason, "category": category}
        impact = _clean(report.get("current_impact"), 200)
        record_event(tid, "priority_reviewed",
                     f"{lifecycle.PRIORITY_LABELS[priority]}: {reason}. Re-evaluated by the priority rules"
                     + (f" from today's impact: {impact}" if impact else ""), actor_type="system", **common)
        done["tasks"].append(_task(ticket, customer, "service", "Recurring problem: send a technician back",
                                   comments or "The original problem returned after service.",
                                   "high", conversation_id, "Priority review and return visit"))
        said.append(f"The ticket is reopened as {lifecycle.PRIORITY_LABELS[priority]} and the service desk will schedule a return visit.")

    elif resolution == "never_fixed":
        ticket = move_ticket(ticket, "escalated")
        record_event(tid, "ticket_escalated", "Customer said the problem was never really fixed",
                     actor_type="customer", **common)
        done["tasks"].append(_task(ticket, customer, "service_manager", "Customer recovery: repair did not hold",
                                   comments or "Customer says the problem was never fixed.", "high",
                                   conversation_id, "Service manager to call the customer"))
        said.append("This is escalated to the service manager, who will call you.")

    else:  # unclear: don't guess, hand it to a person
        record_event(tid, "follow_up_unclear", "The outcome wasn't clear, so a person will follow up",
                     actor_type="system", **common)
        done["tasks"].append(_task(ticket, customer, "service", "Follow-up outcome unclear",
                                   comments or "NightAgent couldn't confirm the outcome.", "normal",
                                   conversation_id, "Call the customer to confirm the repair"))
        said.append("Someone from the service desk will call you to make sure everything is right.")

    # A different problem gets its own ticket, linked back to this one.
    new_issue = _clean(report.get("new_issue_summary"), 300)
    if new_issue:
        category, priority, reason = triage(report.get("new_issue_category"), report.get("new_issue_priority"))
        new = store.create_ticket({
            "customer_id": ticket.get("customer_id"),
            "caller_name": ticket.get("caller_name"),
            "callback_number": ticket.get("callback_number"),
            "issue_summary": new_issue,
            "category": category,
            "priority": priority,
            "priority_reason": reason,
            "status": "awaiting_dispatch",
            "demo": bool(ticket.get("demo")),
            "demo_key_hash": ticket.get("demo_key_hash"),
            "base_status": "awaiting_dispatch",
            "source_ticket_id": tid,
        })
        record_event(new["ticket_id"], "call_received", f"Raised on NightAgent's follow-up call for {tid}: {new_issue}",
                     actor_type="customer", **common)
        record_event(new["ticket_id"], "triage_completed",
                     f"{lifecycle.PRIORITY_LABELS[priority]}: {reason}. Set by the priority rules, not the AI.",
                     actor_type="system", **common)
        record_event(new["ticket_id"], "ticket_created", f"{new['ticket_id']} created. Awaiting dispatch.",
                     actor_type="agent", **common)
        record_event(tid, "new_ticket_created", f"{new['ticket_id']}: {new_issue}", actor_type="system",
                     metadata={"ticket_id": new["ticket_id"]}, **common)
        done["tickets"].append(new)
        said.append(f"I opened a new {lifecycle.PRIORITY_LABELS[priority]} ticket, {new['ticket_id']}, for the new problem.")

    # Sales interest is not service work: open a lead for the account executive.
    interest = _clean(report.get("sales_interest"), 300)
    if interest:
        budget = _clean(report.get("sales_budget"), 80)
        opp = store.create_opportunity({
            "customer_id": ticket.get("customer_id"),
            "contact_name": ticket.get("caller_name"),
            "site_address": (customer or {}).get("site_address"),
            "source_ticket_id": tid,
            "source_conversation_id": conversation_id,
            "type": _clean(report.get("sales_type"), 80) or "System upgrade",
            "scope": _clean(report.get("sales_scope"), 200) or None,
            "interest": interest,
            "device_count": _clean(report.get("sales_device_count"), 40) or None,
            "timeline": _clean(report.get("sales_timeline"), 80) or None,
            "estimated_value": f"Customer-stated budget: {budget}" if budget else VALUE_TBD,
            "assigned_to": DESTINATIONS["account_executive"],
            "demo": bool(ticket.get("demo")),
        })
        record_event(tid, "opportunity_identified", f"{opp['opportunity_id']}: {interest}",
                     actor_type="system", metadata={"opportunity_id": opp["opportunity_id"]}, **common)
        done["opportunities"].append(opp)
        done["tasks"].append(_task(ticket, customer, "account_executive", "New sales opportunity from a service follow-up",
                                   f"{opp['opportunity_id']}: {interest}", "normal", conversation_id,
                                   "AE to qualify scope, timeline, and budget"))
        said.append("I passed your upgrade interest to your account executive, who will reach out.")

    # The customer asked for a person: route to the team they need.
    dept = report.get("callback_department")
    if dept:
        reason = _clean(report.get("callback_reason"), 200) or "Customer asked for a call back"
        done["tasks"].append(_task(ticket, customer, dept if dept in DESTINATIONS else "service",
                                   "Customer requested a call back", reason, "normal", conversation_id,
                                   "Call the customer back"))
        said.append(f"{DESTINATIONS.get(dept, DESTINATIONS['service']).split(',')[0]} will call you back.")

    return {"said": said, "ticket": store.get_ticket(tid), **done}


def follow_up_variables(ticket: dict, token: str) -> dict:
    """Context for the follow-up agent's opening line and prompt. Only what the customer
    already knows about their own ticket; no internal notes or phone numbers."""
    customer = get_store().get_customer(ticket["customer_id"]) if ticket.get("customer_id") else None
    first = (ticket.get("caller_name") or "there").split()[0]
    digits = ticket["ticket_id"].split("-")[1]
    return {
        "customer_first_name": first,
        "business_name": (customer or {}).get("business_name") or "your business",
        "ticket_id": ticket["ticket_id"],
        "ticket_number_spoken": "N S " + " ".join(digits),
        "original_issue": ticket.get("issue_summary") or "the problem you reported",
        "systems_on_site": (customer or {}).get("systems") or "your security system",
        "technician_name": ticket.get("technician_name") or demo.technician_for(ticket.get("priority", "routine")),
        "follow_up_token": token,
    }
