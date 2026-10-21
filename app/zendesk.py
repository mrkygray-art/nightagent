"""Zendesk tickets for calls that made a dispatch board ticket.

After the post-call webhook stores a call, each board ticket made on that call gets a matching Zendesk
ticket, and its Zendesk id is saved on the board row. A note a caller adds later (add_ticket_note) goes
onto that Zendesk ticket as a private comment. Off unless ZENDESK_SUBDOMAIN, ZENDESK_CLIENT_ID and
ZENDESK_CLIENT_SECRET are set. Nothing here may break call logging: every failure is logged and skipped.
"""
import logging
import time

import requests

from app import config, lifecycle

log = logging.getLogger("nightshift")

SCOPE = "tickets:write users:write"
TIMEOUT_SECS = 8  # the webhook waits on this, so keep it short
# Our priorities to Zendesk's (low, normal, high, urgent)
PRIORITIES = {"emergency": "urgent", "urgent": "high", "routine": "normal"}

_token: dict = {"value": "", "expires_at": 0.0}


def configured() -> bool:
    return all([config.ZENDESK_SUBDOMAIN, config.ZENDESK_CLIENT_ID, config.ZENDESK_CLIENT_SECRET])


def subdomain() -> str:
    """Accepts "acme", "acme.zendesk.com" or "https://acme.zendesk.com/", since all three get pasted in."""
    value = config.ZENDESK_SUBDOMAIN.strip().lower().removeprefix("https://").removeprefix("http://")
    return value.split("/")[0].removesuffix(".zendesk.com")


def _base_url() -> str:
    return f"https://{subdomain()}.zendesk.com"


def _access_token() -> str:
    """OAuth client credentials token, reused until a minute before it expires."""
    if _token["value"] and time.time() < _token["expires_at"]:
        return _token["value"]
    res = requests.post(f"{_base_url()}/oauth/tokens", timeout=TIMEOUT_SECS, json={
        "grant_type": "client_credentials",
        "client_id": config.ZENDESK_CLIENT_ID,
        "client_secret": config.ZENDESK_CLIENT_SECRET,
        "scope": SCOPE,
    })
    res.raise_for_status()
    body = res.json()
    # Tokens without expires_in don't expire; refetch hourly anyway in case one is revoked.
    _token.update(value=body["access_token"], expires_at=time.time() + int(body.get("expires_in") or 3600) - 60)
    return _token["value"]


def ticket_payload(ticket: dict, call_summary: str | None) -> dict:
    caller = ticket.get("caller_name") or "Caller (no name given)"
    issue = ticket.get("issue_summary") or "No issue recorded"
    priority = ticket.get("priority")
    lines = [
        f"Caller: {caller}",
        f"Issue: {issue}",
        f"Priority: {lifecycle.PRIORITY_LABELS.get(priority, priority or 'not set')}",
        f"Call summary: {call_summary or 'Not available'}",
        f"NightAgent ticket: {ticket['ticket_id']}",
    ]
    return {"ticket": {
        "subject": f"{caller}: {issue}"[:150],
        # A private note, so creating the ticket never emails anyone
        "comment": {"body": "\n".join(lines), "public": False},
        "priority": PRIORITIES.get(priority, "normal"),
        "tags": ["nightagent"],
        "external_id": ticket["ticket_id"],
    }}


def _send(method: str, path: str, payload: dict):
    def go():
        send = requests.put if method == "PUT" else requests.post
        return send(f"{_base_url()}/api/v2{path}", json=payload,
                    headers={"Authorization": f"Bearer {_access_token()}"}, timeout=TIMEOUT_SECS)

    res = go()
    if res.status_code == 401:  # token revoked or expired early: get a new one once
        _token["value"] = ""
        res = go()
    res.raise_for_status()
    return res


def create_ticket(ticket: dict, call_summary: str | None) -> int:
    return _send("POST", "/tickets.json", ticket_payload(ticket, call_summary)).json()["ticket"]["id"]


def add_note(zendesk_id: int, note: str) -> bool:
    """A caller's note on a ticket that already has a Zendesk twin, as a private comment (no email goes
    out). Returns whether Zendesk took it; a failure is logged, since the note is already on the board."""
    from app.store import in_sandbox
    if in_sandbox() or not configured():
        return False
    try:
        _send("PUT", f"/tickets/{int(zendesk_id)}.json", {"ticket": {
            "comment": {"body": f"Caller added on a NightAgent call: {note}", "public": False},
            "additional_tags": ["nightagent_update"]}})
        return True
    except Exception:  # noqa: BLE001 - Zendesk being down must not break the call
        log.exception("Zendesk: could not add a note to ticket %s", zendesk_id)
        return False


def sync_call(conversation_id: str, call_summary: str | None) -> list[int]:
    """Make a Zendesk ticket for each board ticket from this call that doesn't have one yet."""
    from app.store import get_store, in_sandbox
    if in_sandbox() or not configured():
        return []
    made = []
    try:
        tickets = get_store().tickets_for_call(conversation_id)
    except Exception:  # noqa: BLE001
        log.exception("Zendesk: could not read the board tickets for %s", conversation_id)
        return []
    for ticket in tickets:
        # Already synced (webhook retry) or a demo scenario rather than a real call
        if ticket.get("zendesk_ticket_id") or ticket.get("scenario"):
            continue
        try:
            zendesk_id = create_ticket(ticket, call_summary)
            get_store().update_ticket(ticket["ticket_id"], {"zendesk_ticket_id": zendesk_id})
            log.info("Zendesk ticket %s made for %s", zendesk_id, ticket["ticket_id"])
            made.append(zendesk_id)
        except Exception:  # noqa: BLE001 - Zendesk being down must not break call logging
            log.exception("Zendesk: could not make a ticket for %s", ticket["ticket_id"])
    return made
