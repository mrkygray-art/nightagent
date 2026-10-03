"""Failure injection for the Agent QA Lab: replay a known failure through the real server code
inside a sandbox (a throwaway in-memory store; no real texts), and check what the rules did.

Only the server side is replayed here. What Sam says about it is covered by the ElevenLabs
regression tests on the same page.
"""
from __future__ import annotations

from app.routes_tools import (CreateTicketRequest, LookupRequest, PageRequest, create_ticket,
                              lookup_customer, page_on_call_tech)
from app.store import sandbox


def _step(who: str, did: str, result: dict, keys: tuple[str, ...]) -> dict:
    return {"who": who, "did": did, "result": {k: result[k] for k in keys if k in result}}


def duplicate_caller() -> dict:
    """The same customer calls twice about a gate that's stuck open. Before this fix, the second
    call opened a second ticket for the same problem."""
    steps = []
    with sandbox() as store:
        # Call 1: the first report
        lookup_customer(LookupRequest(query="3105550178", conversation_id="inject_call_1"))
        first = create_ticket(CreateTicketRequest(
            customer_id="C-1002", caller_name="James Carter", callback_number="3105550178",
            issue_summary="Front gate stuck open, won't close.", category="cannot_secure_site",
            suggested_priority="emergency", conversation_id="inject_call_1"))
        steps.append(_step("Call 1 · Sam", "create_ticket: gate stuck open", first,
                           ("ticket_id", "priority", "next_step")))
        paged = page_on_call_tech(PageRequest(ticket_id=first["ticket_id"]))
        steps.append(_step("Call 1 · Sam", "page_on_call_tech", paged, ("paged", "tell_the_caller")))

        # Call 2: someone else at the same site calls about the same gate 20 minutes later
        lookup_customer(LookupRequest(query="3105550178", conversation_id="inject_call_2"))
        second = create_ticket(CreateTicketRequest(
            customer_id="C-1002", caller_name="Dana Carter", callback_number="3105550199",
            issue_summary="The front gate is still stuck open. Is anyone coming?", category="cannot_secure_site",
            suggested_priority="emergency", conversation_id="inject_call_2"))
        steps.append(_step("Call 2 · Sam", "create_ticket: same gate, different caller", second,
                           ("ticket_id", "duplicate_of", "already_alerted", "next_step")))

        # Injected mistake: the model ignores next_step and pages again anyway
        again = page_on_call_tech(PageRequest(ticket_id=second["ticket_id"]))
        steps.append(_step("Injected mistake", "page_on_call_tech again, against instructions", again,
                           ("paged", "message")))

        tickets = [t for t in store.tickets.values() if t.get("customer_id") == "C-1002"]
        events = store.list_events(first["ticket_id"])
        alerts = [e for e in events if e["event_type"] == "technician_paged"]

    checks = [
        ("One ticket for the one problem", len(tickets) == 1, f"{len(tickets)} ticket(s) for Westside Self Storage"),
        ("The second call points to the first ticket", second.get("duplicate_of") == first["ticket_id"],
         f"Second call answered with {second.get('ticket_id')}"),
        ("The second call is in the ticket's history",
         any(e["event_type"] == "caller_called_again" for e in events), "Event: Same problem reported again"),
        ("Sam is told not to alert the technician again",
         "Do NOT call page_on_call_tech" in (second.get("next_step") or ""), "From create_ticket's next_step"),
        ("The technician is alerted once, even when asked twice", len(alerts) == 1,
         f"{len(alerts)} alert(s) sent (simulated)"),
    ]
    return {
        "name": "Same caller twice",
        "before": "Before this fix, the second call opened a second ticket for the same gate and told Sam to "
                  "alert the technician again.",
        "steps": steps,
        "checks": [{"label": label, "passed": bool(ok), "detail": detail} for label, ok, detail in checks],
        "passed": all(ok for _, ok, _ in checks),
    }


SCENARIOS = {"duplicate-caller": duplicate_caller}
