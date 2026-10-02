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
    """Write one history event. Never let a history write break a live call."""
    try:
        return get_store().add_event({
            "ticket_id": ticket_id,
            "event_type": event_type,
            "description": description,
            "simulated": simulated,
            "source": source,
            "occurred_at": occurred_at or now_iso(),
            "conversation_id": conversation_id,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "metadata": metadata or {},
        })
    except Exception:  # noqa: BLE001 - a missing events table must not end the call
        log.exception("Could not record %s event for %s", event_type, ticket_id)
        return None


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
)


def public_ticket(t: dict) -> dict:
    status = lifecycle.normalize_state(t.get("status"))
    out = {k: t.get(k) for k in PUBLIC_TICKET_FIELDS}
    out.update({
        "callback_number": mask_phone(t.get("callback_number")),
        "status": status,
        "status_label": lifecycle.STATE_LABELS[status],
        "priority_label": lifecycle.PRIORITY_LABELS.get(t.get("priority"), t.get("priority")),
        "call_ref": call_ref(t.get("conversation_id")),
        "demo": bool(t.get("demo")),
    })
    return out


def public_event(e: dict) -> dict:
    return {
        "event_type": e["event_type"],
        "label": lifecycle.EVENT_LABELS.get(e["event_type"], e["event_type"].replace("_", " ").capitalize()),
        "description": e.get("description") or "",
        "simulated": bool(e.get("simulated")),
        "occurred_at": e.get("occurred_at"),
    }
