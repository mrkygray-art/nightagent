"""Zendesk -> NightAgent: status and assignee changes on tickets NightAgent made.

A Zendesk trigger (ticket tagged nightagent, status or assignee changed) calls a webhook that posts a small
JSON body to /webhooks/zendesk/ticket-updated. The signature is checked first (HMAC-SHA256 over timestamp +
body, base64, compared in constant time, within a replay window); only then is anything read or written.

What a Zendesk change may do to the board is decided here, not in Zendesk:
- Only the moves in MOVES are made, and each is checked again by the lifecycle, so a Zendesk change can
  never skip a stage. A change that would need a skip is refused and recorded; the board stays put.
- Zendesk never changes the board's priority, so an emergency can't be lowered from Zendesk.
- Repeats are ignored: a delivery no newer than what the board already has (same updated_at, status and
  assignee, or an older updated_at) changes nothing. Zendesk retries and can deliver the same event twice.
- Changes made by our own integration user are ignored, so a note NightAgent adds can't loop back.

The Zendesk status and assignee are stored for the board and the sidebar card. The trigger sends only the
assignee's id (no free text, so a quote in a name can't break the JSON); the name is looked up through the API
when the assignee changes, and shown only on the staff-only sidebar card. Sam never hears the assignee:
check_ticket_status speaks only lifecycle labels, and refused-change events are left out of it.
"""
import base64
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

from app import config, lifecycle, zendesk
from app.service import record_event
from app.store import get_store

log = logging.getLogger("nightshift")

SIGNATURE_HEADER = "X-Zendesk-Webhook-Signature"
TIMESTAMP_HEADER = "X-Zendesk-Webhook-Signature-Timestamp"  # e.g. 2021-03-25T05:09:27Z
INVOCATION_HEADER = "X-Zendesk-Webhook-Invocation-Id"
REPLAY_WINDOW = timedelta(minutes=10)  # Zendesk retries timeouts up to five times; a replay inside it is a repeat
FUTURE_SKEW = timedelta(minutes=1)
TAG = "nightagent"

# Zendesk's standard statuses ({{ticket.status}} renders them capitalized, "On-hold" with a hyphen)
STATUSES = {"new", "open", "pending", "hold", "solved", "closed"}
STATUS_LABELS = {"new": "New", "open": "Open", "pending": "Pending", "hold": "On hold", "solved": "Solved",
                 "closed": "Closed"}

# The allow-list: (what happened in Zendesk, where the board is) -> (where the board goes, event to record).
MOVES = {
    ("assigned", "awaiting_dispatch"): ("technician_assigned", "technician_assigned", "Assigned in Zendesk."),
    ("assigned", "dispatched"): ("technician_assigned", "technician_assigned", "Assigned in Zendesk."),
    ("assigned", "escalated"): ("technician_assigned", "technician_assigned", "Assigned in Zendesk."),
    ("solved", "onsite"): ("work_completed", "work_completed", "Marked solved in Zendesk."),
    ("closed", "resolved"): ("closed", "ticket_closed", "Closed in Zendesk."),
    ("open", "resolved"): ("reopened", "ticket_reopened", "Reopened in Zendesk."),
    ("open", "closed"): ("reopened", "ticket_reopened", "Reopened in Zendesk."),
}
# Board states where the Zendesk change is already true, so it's only mirrored (a reassignment, say).
# A change in neither MOVES nor here would need the board to skip a stage, and is refused.
_PAST_ASSIGNED = {"technician_assigned", "en_route", "onsite", "work_completed", "follow_up_pending", "resolved",
                  "closed"}
ALREADY = {
    "assigned": _PAST_ASSIGNED,
    "solved": {"work_completed", "follow_up_pending", "resolved", "closed"},
    "closed": {"closed"},
}
# Board-moving words for the refused-change note
IMPLIES = {"assigned": "technician_assigned", "solved": "work_completed", "closed": "closed"}
REFUSED_EVENT = "zendesk_update_refused"


def configured() -> bool:
    return bool(config.ZENDESK_WEBHOOK_SECRET and config.ZENDESK_INTEGRATION_USER_ID.strip())


def _parse_time(value: str | None) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        if value.isdigit():  # epoch seconds, in case the timestamp comes that way
            return datetime.fromtimestamp(int(value), timezone.utc)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def sign(body: bytes, timestamp: str, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()).decode()


def verify(body: bytes, signature: str | None, timestamp: str | None, secret: str,
           now: datetime | None = None) -> bool:
    """Zendesk's signature: base64(HMAC-SHA256(secret, timestamp + body)), with the timestamp inside the window."""
    if not (secret and signature and timestamp):
        return False
    sent = _parse_time(timestamp)
    if not sent:
        return False
    age = (now or datetime.now(timezone.utc)) - sent
    if age > REPLAY_WINDOW or age < -FUTURE_SKEW:
        return False
    return hmac.compare_digest(sign(body, timestamp, secret).encode(), signature.strip().encode())


def _status(value) -> str | None:
    word = str(value or "").strip().lower().replace("on-hold", "hold").replace("on hold", "hold")
    return word if word in STATUSES else None


def _id(value) -> str | None:
    text = str(value or "").strip()
    return text if text.isdigit() else None


def _ignored(reason: str) -> dict:
    return {"result": "ignored", "reason": reason}


def apply_update(payload: dict, lookup_name=None) -> dict:
    """Apply one verified Zendesk delivery. Returns what happened: applied, mirrored, refused, duplicate,
    or ignored (with why). Raises only if the store fails, so the caller can ask Zendesk to retry.
    lookup_name(assignee_id) -> name defaults to the Zendesk API; the Evaluation Lab's sandbox passes its own."""
    if not isinstance(payload, dict):
        return _ignored("Body isn't a JSON object")
    tags = str(payload.get("tags") or "").lower().replace(",", " ").split()
    if TAG not in tags:
        return _ignored("Not tagged nightagent")
    by = _id(payload.get("updated_by_id"))
    if by and by == config.ZENDESK_INTEGRATION_USER_ID.strip():
        return _ignored("Made by NightAgent's own integration user")
    zendesk_id = _id(payload.get("zendesk_ticket_id"))
    nightagent_id = str(payload.get("nightagent_ticket_id") or "").strip().upper()
    store = get_store()
    ticket = store.get_ticket(nightagent_id) if nightagent_id else None
    # The custom field names the board ticket; the board row must also point back at this Zendesk ticket,
    # so a field typed onto some other Zendesk ticket can't move a board ticket.
    if not ticket or not zendesk_id or str(ticket.get("zendesk_ticket_id") or "") != zendesk_id:
        return _ignored("No board ticket matches this Zendesk ticket")

    status = _status(payload.get("status"))
    if not status:
        return _ignored("Unknown Zendesk status")
    assignee_id = _id(payload.get("assignee_id"))
    updated_at = _parse_time(payload.get("updated_at"))
    if not updated_at:
        return _ignored("No updated_at")

    stored_at = _parse_time(ticket.get("zendesk_updated_at"))
    same = (status == ticket.get("zendesk_status") and assignee_id == _id(ticket.get("zendesk_assignee_id")))
    if stored_at and (updated_at < stored_at or (updated_at == stored_at and same)):
        return {"result": "duplicate", "reason": "Already have this change or a newer one"}

    # The name, only for the staff sidebar: kept while the assignee stays the same, looked up when it changes
    assignee_name = None
    if assignee_id:
        if assignee_id == _id(ticket.get("zendesk_assignee_id")) and ticket.get("zendesk_assignee_name"):
            assignee_name = ticket["zendesk_assignee_name"]
        else:
            assignee_name = (lookup_name or zendesk.user_name)(assignee_id)

    signals = []
    if assignee_id and assignee_id != _id(ticket.get("zendesk_assignee_id")):
        signals.append("assigned")
    if status != ticket.get("zendesk_status"):
        signals.append(status)

    state = lifecycle.normalize_state(ticket.get("status"))
    moves, refused = [], []
    for signal in signals:
        move = MOVES.get((signal, state))
        if move:
            lifecycle.check_transition(state, move[0])  # the lifecycle has the last word
            moves.append(move)
            state = move[0]
        elif signal in IMPLIES and state not in ALREADY[signal]:
            refused.append(signal)

    fields = {"zendesk_status": status, "zendesk_assignee_id": int(assignee_id) if assignee_id else None,
              "zendesk_assignee_name": assignee_name, "zendesk_updated_at": updated_at.isoformat()}
    if moves:
        fields["status"] = state
    store.update_ticket(ticket["ticket_id"], fields)  # one write, so a retry after it is a duplicate

    tid = ticket["ticket_id"]
    for _target, event_type, description in moves:
        record_event(tid, event_type, description, source="zendesk", actor_type="staff")
    shown = lifecycle.STATE_LABELS[state]
    for signal in refused:
        wanted = lifecycle.STATE_LABELS[IMPLIES[signal]]
        record_event(tid, REFUSED_EVENT,
                     f"Zendesk said {STATUS_LABELS.get(signal, 'assigned').lower()}, which would mean "
                     f"\"{wanted}\", but the ticket is at \"{shown}\". A Zendesk change can't skip a stage, "
                     "so the board didn't move.", source="zendesk", actor_type="staff",
                     metadata={"zendesk_status": status, "board_status": state})
    if moves:
        log.info("Zendesk %s moved %s to %s", zendesk_id, tid, state)
    result = "applied" if moves else "refused" if refused else "mirrored"
    return {"result": result, "board_status": state, "zendesk_status": status,
            "moved": [m[0] for m in moves], "refused": refused}
