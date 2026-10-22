"""Failure injection for the Evaluation Lab: replay a known failure through the real server code
inside a sandbox (a throwaway in-memory store; no real texts), and check what the rules did.

Only the server side is replayed here. What Sam says about it is covered by the ElevenLabs
regression tests on the same page.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app import zendesk_sync
from app.notify import paging_down
from app.routes_tools import (CreateTicketRequest, LookupRequest, PageRequest, TicketStatusRequest, create_ticket,
                              lookup_customer, page_on_call_tech, ticket_status)
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


def paging_service_down() -> dict:
    """The service that texts the on-call technician is down during an emergency call. Before this
    fix, the paging error crashed the tool call: Sam got a bare error and the ticket's history never
    showed that the alert failed."""
    steps = []
    with sandbox() as store:
        lookup_customer(LookupRequest(query="4245550119", conversation_id="inject_down_1"))
        made = create_ticket(CreateTicketRequest(
            customer_id="C-1003", caller_name="Priya Shah", callback_number="4245550119",
            issue_summary="Main entrance won't unlock; nobody can get in.", category="entry_blocked",
            suggested_priority="emergency", conversation_id="inject_down_1"))
        tid = made["ticket_id"]
        steps.append(_step("Sam", "create_ticket: main entrance won't unlock", made, ("ticket_id", "priority", "next_step")))
        with paging_down():
            first = page_on_call_tech(PageRequest(ticket_id=tid))
            steps.append(_step("Injected failure", "page_on_call_tech while the paging service is down", first,
                               ("paged", "alert_failed", "next_step")))
            retry = page_on_call_tech(PageRequest(ticket_id=tid))
            steps.append(_step("Sam", "page_on_call_tech, one retry (still down)", retry, ("paged", "alert_failed")))
        saved = store.get_ticket(tid) is not None
        alerted_while_down = bool((store.get_ticket(tid) or {}).get("paged_at"))
        back = page_on_call_tech(PageRequest(ticket_id=tid))
        steps.append(_step("Later", "page_on_call_tech after the service is back", back, ("paged", "tell_the_caller")))
        events = store.list_events(tid)

    failed = [e for e in events if e["event_type"] == "page_failed"]
    sent = [e for e in events if e["event_type"] == "technician_paged"]
    checks = [
        ("The call keeps going: the tool answers instead of crashing", first.get("alert_failed") is True,
         "page_on_call_tech returned alert_failed"),
        ("The ticket is still saved", saved, f"{tid} is on the board"),
        ("The failure is in the ticket's history", len(failed) == 2, f"{len(failed)} \"Alert didn't go through\" event(s)"),
        ("Sam is told not to promise a callback time",
         "Do not promise a callback time" in (first.get("next_step") or ""), "From page_on_call_tech's next_step"),
        ("The ticket isn't marked as alerted while the alert is failing", not alerted_while_down,
         "No alert time saved"),
        ("Once the service is back, the alert goes through once", back.get("paged") is True and len(sent) == 1,
         f"{len(sent)} alert(s) sent (simulated)"),
    ]
    return {
        "name": "Alert service down",
        "before": "Before this fix, a paging error crashed the tool call: Sam got a bare error and the ticket's "
                  "history never showed that the alert failed.",
        "steps": steps,
        "checks": [{"label": label, "passed": bool(ok), "detail": detail} for label, ok, detail in checks],
        "passed": all(ok for _, ok, _ in checks),
    }


# A throwaway signing secret for the sandbox: the real webhook secret never leaves the server config.
_LAB_SECRET = "evaluation-lab-sandbox-secret"
_LAB_ASSIGNEE = "Morgan Reyes"  # made up, like the rest of the demo data


def _zendesk_ticket(store, zendesk_id: int) -> str:
    """An emergency board ticket that NightAgent already logged in Zendesk (made through the real tool)."""
    made = create_ticket(CreateTicketRequest(
        customer_id="C-1003", caller_name="Priya Shah", callback_number="4245550119",
        issue_summary="Main entrance won't unlock; nobody can get in.", category="entry_blocked",
        suggested_priority="emergency", conversation_id=f"inject_zd_{zendesk_id}"))
    store.update_ticket(made["ticket_id"], {"zendesk_ticket_id": zendesk_id})
    return made["ticket_id"]


def _stamp(minutes_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _delivery(payload: dict) -> tuple[bytes, str, str]:
    """A signed webhook body, the way Zendesk sends one."""
    body = json.dumps(payload).encode()
    stamp = _stamp()
    return body, zendesk_sync.sign(body, stamp, _LAB_SECRET), stamp


def _deliver(body: bytes, signature: str, stamp: str) -> dict:
    """What the endpoint does after reading the request: check the signature, then apply."""
    if not zendesk_sync.verify(body, signature, stamp, _LAB_SECRET):
        return {"result": "rejected", "reason": "Invalid signature"}
    return zendesk_sync.apply_update(json.loads(body))


def _payload(tid: str, zendesk_id: int, status: str, minutes_ago: int, assignee: bool = True, **extra) -> dict:
    return {"zendesk_ticket_id": str(zendesk_id), "nightagent_ticket_id": tid, "status": status,
            "assignee_id": "7001" if assignee else "", "assignee_name": _LAB_ASSIGNEE if assignee else "",
            "updated_by_id": "7001", "updated_at": _stamp(minutes_ago), "tags": "nightagent", **extra}


def _sam_says(tid: str) -> dict:
    return ticket_status(TicketStatusRequest(ticket_id=tid, customer_id="C-1003", conversation_id="inject_zd_status"))


def _result(name: str, before: str, steps: list, checks: list) -> dict:
    return {"name": name, "before": before, "steps": steps,
            "checks": [{"label": label, "passed": bool(ok), "detail": detail} for label, ok, detail in checks],
            "passed": all(ok for _, ok, _ in checks)}


def zendesk_duplicate_delivery() -> dict:
    """Zendesk delivers the same webhook twice (it retries after a timeout, and says a webhook can fire more
    than once for one change), then an older delivery arrives late."""
    steps = []
    with sandbox() as store:
        tid = _zendesk_ticket(store, 8101)
        delivery = _delivery(_payload(tid, 8101, "Open", minutes_ago=1))
        first = _deliver(*delivery)
        steps.append(_step("Zendesk", "Webhook: an agent assigned the ticket", first, ("result", "board_status", "moved")))
        again = _deliver(*delivery)
        steps.append(_step("Zendesk", "The same webhook again, same signature (a retry)", again, ("result", "reason")))
        late = _deliver(*_delivery(_payload(tid, 8101, "New", minutes_ago=5, assignee=False)))
        steps.append(_step("Zendesk", "An older change arriving late (still unassigned)", late, ("result", "reason")))
        said = _sam_says(tid)
        steps.append(_step("Caller · Sam", "check_ticket_status", said, ("status", "tell_the_caller")))
        ticket = store.get_ticket(tid)
        assigned = [e for e in store.list_events(tid) if e["event_type"] == "technician_assigned"]

    checks = [
        ("The first delivery moves the board one step", first.get("moved") == ["technician_assigned"],
         f"Board: {first.get('board_status')}"),
        ("The retry changes nothing", again.get("result") == "duplicate", again.get("reason") or again.get("result")),
        ("The late, older delivery changes nothing", late.get("result") == "duplicate",
         late.get("reason") or late.get("result")),
        ('One "Technician assigned" in the history', len(assigned) == 1, f"{len(assigned)} event(s)"),
        ("The board keeps the newest Zendesk state",
         ticket.get("zendesk_status") == "open" and ticket.get("status") == "technician_assigned",
         f"Zendesk: {ticket.get('zendesk_status')}"),
        ("Sam doesn't say who was assigned", _LAB_ASSIGNEE.split()[0] not in json.dumps(said),
         "Assignee's name not in the tool result"),
    ]
    return _result("Zendesk webhook delivered twice",
                   "New with the Zendesk sync, so there's no earlier behavior to compare: Zendesk's docs say a webhook "
                   "can fire more than once for one change, and it retries after a timeout.", steps, checks)


def zendesk_illegal_transition() -> dict:
    """In Zendesk someone marks an emergency solved (and its priority low) while the board still has it
    waiting for a technician. On the board that would skip four stages."""
    steps = []
    with sandbox() as store:
        tid = _zendesk_ticket(store, 8102)
        tried = _deliver(*_delivery(_payload(tid, 8102, "Solved", minutes_ago=1, assignee=False, priority="Low")))
        steps.append(_step("Zendesk", "Webhook: marked solved, priority set to low, nobody assigned", tried,
                           ("result", "board_status", "refused")))
        said = _sam_says(tid)
        steps.append(_step("Caller · Sam", "check_ticket_status", said, ("status", "tell_the_caller")))
        ticket = store.get_ticket(tid)
        refused = [e for e in store.list_events(tid) if e["event_type"] == zendesk_sync.REFUSED_EVENT]

    checks = [
        ("The board doesn't skip ahead", ticket.get("status") == "awaiting_dispatch", f"Board: {ticket.get('status')}"),
        ("The emergency stays an emergency", ticket.get("priority") == "emergency", f"Priority: {ticket.get('priority')}"),
        ("The refusal is in the ticket's history", len(refused) == 1,
         f'{len(refused)} "Zendesk change not applied" event(s)'),
        ("What Zendesk said is still recorded", ticket.get("zendesk_status") == "solved",
         f"Zendesk: {ticket.get('zendesk_status')}"),
        ("Sam still gives the board's status",
         said.get("status") == "Waiting for a technician" and "not applied" not in (said.get("tell_the_caller") or ""),
         said.get("status") or ""),
    ]
    return _result("Zendesk tries to skip ahead",
                   'New with the Zendesk sync, so there\'s no earlier behavior to compare: without the allow-list, a '
                   'Zendesk "Solved" would have marked the repair finished on an emergency nobody had gone to.', steps, checks)


SCENARIOS = {"duplicate-caller": duplicate_caller, "paging-down": paging_service_down,
             "zendesk-duplicate": zendesk_duplicate_delivery, "zendesk-skip": zendesk_illegal_transition}
