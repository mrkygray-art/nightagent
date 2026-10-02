"""Lifecycle actions shared by the voice tools and the demo page: record events, move a
ticket to a new state, and shape tickets for the public page."""
import hashlib
import logging
from datetime import datetime, timedelta

from app import lifecycle
from app.store import get_store, now_iso

log = logging.getLogger("nightshift")


def record_event(ticket_id: str, event_type: str, description: str = "", *, simulated: bool = False,
                 source: str = "call", occurred_at: str | None = None, conversation_id: str | None = None,
                 actor_type: str = "system", actor_id: str | None = None,
                 metadata: dict | None = None) -> dict | None:
    """Write one history event. Never let a history write break a live call.

    Without an explicit time, the event lands at "now" or just after the ticket's latest event,
    whichever is later, so the timeline stays in order even after demo-clock steps."""
    try:
        if not occurred_at:
            occurred_at = now_iso()
            events = get_store().list_events(ticket_id)
            if events and datetime.fromisoformat(events[-1]["occurred_at"]) > datetime.fromisoformat(occurred_at):
                occurred_at = events[-1]["occurred_at"]
        return get_store().add_event({
            "ticket_id": ticket_id,
            "event_type": event_type,
            "description": description,
            "simulated": simulated,
            "source": source,
            "occurred_at": occurred_at,
            "conversation_id": conversation_id,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "metadata": metadata or {},
        })
    except Exception:  # noqa: BLE001 - a missing events table must not end the call
        log.exception("Could not record %s event for %s", event_type, ticket_id)
        return None


def log_tool_call(tool: str, outcome: str = "", *, conversation_id: str | None = None,
                  ticket_id: str | None = None, called_at: str | None = None) -> None:
    """Note one tool call for the call report. Like events, this must never break a live call."""
    try:
        get_store().add_tool_call({
            "tool": tool,
            "outcome": outcome[:200],
            "conversation_id": conversation_id or None,
            "ticket_id": ticket_id,
            "called_at": called_at or now_iso(),
        })
    except Exception:  # noqa: BLE001
        log.exception("Could not log the %s tool call", tool)


def move_ticket(ticket: dict, target: str, extra: dict | None = None) -> dict:
    """Move a ticket to `target` if the lifecycle allows it. Raises TransitionError otherwise."""
    lifecycle.check_transition(ticket.get("status"), target)
    fields = {"status": target, **(extra or {})}
    get_store().update_ticket(ticket["ticket_id"], fields)
    return {**ticket, **fields}


def shift(iso: str, minutes: int) -> str:
    return (datetime.fromisoformat(iso) + timedelta(minutes=minutes)).isoformat()


def call_ref(conversation_id: str | None) -> str | None:
    """A short fingerprint of the conversation id, so the page can spot "your call"
    without the public feed handing out conversation ids."""
    if not conversation_id:
        return None
    return hashlib.sha256(conversation_id.encode()).hexdigest()[:16]


def mask_phone(number: str | None) -> str:
    digits = "".join(ch for ch in (number or "") if ch.isdigit())
    return f"(•••) •••-{digits[-4:]}" if len(digits) >= 4 else "—"


PUBLIC_TICKET_FIELDS = (
    "ticket_id", "customer_id", "caller_name", "issue_summary", "category", "priority",
    "priority_reason", "paged_at", "created_at", "demo", "scenario", "technician_name",
    "source_ticket_id", "resolution", "csat",
)


def public_ticket(t: dict) -> dict:
    status = lifecycle.normalize_state(t.get("status"))
    out = {k: t.get(k) for k in PUBLIC_TICKET_FIELDS}
    out.update({
        "callback_number": mask_phone(t.get("callback_number")),
        "status": status,
        "status_label": lifecycle.STATE_LABELS[status],
        "priority_label": lifecycle.PRIORITY_LABELS.get(t.get("priority"), t.get("priority")),
        "priority_reason": lifecycle.plain_words(t.get("priority_reason")) or None,
        "call_ref": call_ref(t.get("conversation_id")),
        "demo": bool(t.get("demo")),
    })
    return out


def public_task(t: dict) -> dict:
    keys = ("task_id", "destination", "assigned_to", "reason", "summary", "priority",
            "requested_follow_up", "status", "created_at")
    return {k: t.get(k) for k in keys}


def public_message(t: dict) -> dict:
    from app.follow_up import DEPARTMENT_LABELS  # here to avoid an import loop
    return {
        "message_id": t["task_id"],
        "department": DEPARTMENT_LABELS.get(t.get("destination"), t.get("destination")),
        "assigned_to": t.get("assigned_to"),
        "person_requested": t.get("person_requested"),
        "summary": t.get("summary"),
        "contact_name": t.get("contact_name"),
        "callback_number": mask_phone(t.get("callback_number")),
        "best_time": t.get("best_time"),
        "status": t.get("status"),
        "created_at": t.get("created_at"),
        "call_ref": call_ref(t.get("source_conversation_id")),
    }


def public_opportunity(o: dict) -> dict:
    keys = ("opportunity_id", "type", "scope", "interest", "device_count", "timeline",
            "estimated_value", "assigned_to", "status", "created_at")
    return {k: o.get(k) for k in keys}


def public_event(e: dict) -> dict:
    label = lifecycle.EVENT_LABELS.get(e["event_type"], e["event_type"].replace("_", " ").capitalize())
    description = lifecycle.plain_words(e.get("description"))
    # "Problem saved: High priority" reads better than burying the priority in the details.
    if e["event_type"] in ("triage_completed", "priority_reviewed"):
        for word in lifecycle.PRIORITY_LABELS.values():
            if description.startswith(word + ": "):
                label, description = f"{label}: {word}", description[len(word) + 2:]
                break
    return {
        "event_type": e["event_type"],
        "label": label,
        "description": description,
        "simulated": bool(e.get("simulated")),
        "occurred_at": e.get("occurred_at"),
    }
