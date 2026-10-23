"""Zendesk tickets for calls that made a dispatch board ticket.

After the post-call webhook stores a call, each board ticket made on that call gets a matching Zendesk
ticket, and its Zendesk id is saved on the board row. A note a caller adds later (add_ticket_note) goes
onto that Zendesk ticket as a private comment. Off unless ZENDESK_SUBDOMAIN, ZENDESK_CLIENT_ID and
ZENDESK_CLIENT_SECRET are set. Nothing here may break call logging: every failure is logged and skipped.

Who a ticket is from: each caller is a Zendesk end user (create_or_update, keyed by an external id made of the
NightAgent customer_id and a slug of their name; no phone number or email is ever sent), each customer account
is a Zendesk organization (external id = customer_id), and the user joins it through Organization Memberships.
A caller with no name, or with no matching account, goes under an "Unknown caller" user (one per account, and
one with no organization for callers without an account). If a user or organization step fails, the ticket is
still made, just without that part; if Zendesk refuses the ticket itself (a bad field id or value), it is made
the old way, with the API user as requester and no custom fields.
"""
import hashlib
import logging
import re
import time
import unicodedata

import requests

from app import config, deepgram_voice, lifecycle, review as review_rules

log = logging.getLogger("nightshift")

# organizations:write also covers memberships; users:read looks up an assignee's name for the status sync
SCOPE = "tickets:write users:write users:read organizations:write"
# What the OAuth client had before organizations. If the client's allowed scopes leave out organizations:write,
# Zendesk refuses the wider token (400 invalid_scope); tickets then still go in with this one.
BASIC_SCOPE = "tickets:write users:write"
TIMEOUT_SECS = 8  # the webhook waits on this, so keep it short
# Our priorities to Zendesk's (low, normal, high, urgent)
PRIORITIES = {"emergency": "urgent", "urgent": "high", "routine": "normal"}
ZENDESK_PRIORITIES = ["low", "normal", "high", "urgent"]
UNKNOWN_CALLER = "Unknown caller"
UNKNOWN_SLUG = "unknown-caller"
CALL_SOURCE = "nightagent_phone"  # the call source field's value: every synced ticket comes from a live call

_token: dict = {"value": "", "expires_at": 0.0, "scope": SCOPE}


class ZendeskError(Exception):
    def __init__(self, status: int, path: str):
        super().__init__(f"Zendesk answered {status} for {path}")
        self.status = status


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

    def ask(scope: str):
        return requests.post(f"{_base_url()}/oauth/tokens", timeout=TIMEOUT_SECS, json={
            "grant_type": "client_credentials",
            "client_id": config.ZENDESK_CLIENT_ID,
            "client_secret": config.ZENDESK_CLIENT_SECRET,
            "scope": scope,
        })

    res = ask(_token["scope"])
    if res.status_code == 400 and _token["scope"] != BASIC_SCOPE:
        log.warning("Zendesk refused the token scope %r; using %r, so no organizations", _token["scope"], BASIC_SCOPE)
        _token["scope"] = BASIC_SCOPE
        res = ask(BASIC_SCOPE)
    res.raise_for_status()
    body = res.json()
    # Tokens without expires_in don't expire; refetch hourly anyway in case one is revoked.
    _token.update(value=body["access_token"], expires_at=time.time() + int(body.get("expires_in") or 3600) - 60)
    return _token["value"]


def ticket_payload(ticket: dict, call_summary: str | None, review: dict | None = None) -> dict:
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
    zd_priority, tags = PRIORITIES.get(priority, "normal"), ["nightagent"]
    if deepgram_voice.is_deepgram(ticket.get("conversation_id")):
        lines.append("Voice: Sam on Deepgram (Flux, Aura-2, Claude)")
        tags.append("deepgram")
    if review and review["reviewNeeded"]:
        lines.append(review_rules.note_line(review))
        # A reason's tag is also its option's value in the Review reason field, so the two always agree
        tags += ["needs_review", *(r["code"].lower() for r in review["reasons"])]
        if review["bump_priority"]:  # Zendesk only: the board keeps the rules' priority
            zd_priority = ZENDESK_PRIORITIES[min(ZENDESK_PRIORITIES.index(zd_priority) + 1, len(ZENDESK_PRIORITIES) - 1)]
    return {"ticket": {
        "subject": f"{caller}: {issue}"[:150],
        # A private note, so creating the ticket never emails anyone
        "comment": {"body": "\n".join(lines), "public": False},
        "priority": zd_priority,
        "tags": tags,
        "external_id": ticket["ticket_id"],
    }}


def _send(method: str, path: str, payload: dict, idempotency_key: str | None = None):
    def go():
        send = requests.put if method == "PUT" else requests.post
        headers = {"Authorization": f"Bearer {_access_token()}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return send(f"{_base_url()}/api/v2{path}", json=payload, headers=headers, timeout=TIMEOUT_SECS)

    res = go()
    if res.status_code == 401:  # token revoked or expired early: get a new one once
        _token["value"] = ""
        res = go()
    if res.status_code >= 400:
        raise ZendeskError(res.status_code, path)
    return res


LOOKUP_TIMEOUT_SECS = 3  # runs inside the Zendesk webhook, which Zendesk gives 12 seconds in all


def user_name(user_id: int | str) -> str | None:
    """A Zendesk agent's name, looked up by id, for the staff-only sidebar card. The status webhook sends only
    the assignee's id, so a name with quotes in it can't break its JSON body. None if it can't be had; the
    status change is applied either way."""
    from app.store import in_sandbox
    if in_sandbox() or not configured():
        return None
    path = f"/users/{int(user_id)}.json"
    try:
        def go():
            return requests.get(f"{_base_url()}/api/v2{path}", timeout=LOOKUP_TIMEOUT_SECS,
                                headers={"Authorization": f"Bearer {_access_token()}"})

        res = go()
        if res.status_code == 401:  # token revoked or expired early: get a new one once
            _token["value"] = ""
            res = go()
        if res.status_code >= 400:
            raise ZendeskError(res.status_code, path)
        return " ".join(str(res.json()["user"].get("name") or "").split())[:100] or None
    except Exception:  # noqa: BLE001 - the name is a nicety; the sync must still go through
        log.exception("Zendesk: could not look up the name of user %s", user_id)
        return None


def slug(name: str) -> str:
    """"José O'Brien" -> "jose-o-brien". A name with no Latin letters at all gets a short hash instead."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    out = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:60].strip("-")
    return out or "n-" + hashlib.sha256(" ".join(name.lower().split()).encode()).hexdigest()[:10]


def requester_identity(ticket: dict) -> tuple[str, str]:
    """(external_id, name) of the Zendesk user a board ticket is from."""
    from app.routes_tools import given  # here, since routes_tools imports this module
    name = given(ticket.get("caller_name"), 100)
    customer_id = ticket.get("customer_id")
    if not customer_id:
        return UNKNOWN_SLUG, UNKNOWN_CALLER
    if not name:
        return f"{customer_id}:{UNKNOWN_SLUG}", UNKNOWN_CALLER
    return f"{customer_id}:{slug(name)}", name


def _organization(customer_id: str) -> int | None:
    from app.store import get_store
    _access_token()  # learns whether the token covers organizations
    if _token["scope"] != SCOPE:
        return None
    customer = get_store().get_customer(customer_id) or {}
    org = {"external_id": customer_id, "name": customer.get("business_name") or customer_id}
    return _send("POST", "/organizations/create_or_update", {"organization": org}).json()["organization"]["id"]


def _requester(ticket: dict) -> tuple[int | None, int | None]:
    """(user id, organization id) for the ticket. Either is None if that step failed or doesn't apply. The
    organization id is only given once the user is surely a member, since Zendesk refuses any other."""
    org_id = None
    customer_id = ticket.get("customer_id")
    if customer_id:
        try:
            org_id = _organization(customer_id)
        except Exception:  # noqa: BLE001
            log.exception("Zendesk: could not create or update the organization for %s", customer_id)
    external_id, name = requester_identity(ticket)
    try:
        # Name and external id only: the callback number never goes to Zendesk, and there is no email.
        user = _send("POST", "/users/create_or_update", {"user": {
            "external_id": external_id, "name": name, "role": "end-user"}}).json()["user"]
    except Exception:  # noqa: BLE001
        log.exception("Zendesk: could not create or update the requester for %s", ticket["ticket_id"])
        return None, None
    # A user's organization_id is their default organization; a caller's user only ever joins their own.
    if org_id and user.get("organization_id") != org_id:
        try:
            _send("POST", "/organization_memberships", {"organization_membership": {
                "user_id": user["id"], "organization_id": org_id}})
        except Exception:  # noqa: BLE001 - a 422 can also mean "already a member"; the ticket then takes the default
            log.exception("Zendesk: could not add the requester for %s to organization %s", ticket["ticket_id"], org_id)
            org_id = None
    return user["id"], org_id


def custom_fields(ticket: dict, review: dict | None = None) -> list[dict]:
    wanted = [("ZENDESK_FIELD_NIGHTAGENT_ID", ticket["ticket_id"]), ("ZENDESK_FIELD_CATEGORY", ticket.get("category")),
              ("ZENDESK_FIELD_CALL_SOURCE", CALL_SOURCE)]
    if review and review["reviewNeeded"]:
        wanted += [("ZENDESK_FIELD_REVIEW_NEEDED", True),
                   ("ZENDESK_FIELD_REVIEW_REASON", [r["code"].lower() for r in review["reasons"]]),
                   ("ZENDESK_FIELD_RECOMMENDED_OPTIONS", review_rules.options_text(review))]
    fields = []
    for setting, value in wanted:
        field_id = getattr(config, setting).strip()
        if not field_id or value is None:
            continue
        if not field_id.isdigit():
            log.warning("Zendesk: %s is not a field id (a number), so that field is left off", setting)
            continue
        fields.append({"id": int(field_id), "value": value})
    return fields


def create_ticket(ticket: dict, call_summary: str | None, review: dict | None = None) -> int:
    """The ticket with its requester, organization and custom fields, or the old way if Zendesk refuses that.

    Retries are safe: each try sends an Idempotency-Key made from the NightAgent ticket id, so a repeat with the
    same body gets back the ticket already made (Zendesk keeps keys for two hours). The old-way ticket has its
    own key and is only tried after a 422, when Zendesk has said no and made nothing."""
    plain = ticket_payload(ticket, call_summary, review)
    user_id, org_id = _requester(ticket)
    full = {"ticket": dict(plain["ticket"])}
    if user_id:
        full["ticket"]["requester_id"] = user_id
        # The submitter always authors a new ticket's first comment, and on these tickets Zendesk made that the
        # caller. Naming NightAgent's own integration user keeps the private note from reading as the caller's.
        submitter = config.ZENDESK_INTEGRATION_USER_ID.strip()
        if submitter.isdigit():
            full["ticket"]["submitter_id"] = int(submitter)
    if org_id:
        full["ticket"]["organization_id"] = org_id
    if fields := custom_fields(ticket, review):
        full["ticket"]["custom_fields"] = fields
    key = f"nightagent-{ticket['ticket_id']}"
    if full == plain:
        return _send("POST", "/tickets.json", plain, key).json()["ticket"]["id"]
    try:
        return _send("POST", "/tickets.json", full, key).json()["ticket"]["id"]
    except ZendeskError as e:
        # Only a 422 is a sure "no ticket made". After a timeout or a 5xx the ticket may exist, and a second,
        # different request could make a duplicate, so those go to the caller's error log instead.
        if e.status != 422:
            raise
        log.warning("Zendesk refused %s with requester and fields (422); making it the old way", ticket["ticket_id"])
    return _send("POST", "/tickets.json", plain, f"{key}-plain").json()["ticket"]["id"]


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


def sync_call(conversation_id: str, call_summary: str | None, analysis: dict | None = None) -> list[int]:
    """Make a Zendesk ticket for each board ticket from this call that doesn't have one yet. analysis is the
    analyzed call (evaluation.analyze), which the human-review rules read."""
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
            review = None
            try:
                review = review_rules.evaluate_review(review_rules.call_data(ticket, analysis, get_store()))
            except Exception:  # noqa: BLE001 - the ticket still goes in, just without the review flags
                log.exception("Zendesk: could not evaluate the review rules for %s", ticket["ticket_id"])
            zendesk_id = create_ticket(ticket, call_summary, review)
            get_store().update_ticket(ticket["ticket_id"], {"zendesk_ticket_id": zendesk_id})
            log.info("Zendesk ticket %s made for %s", zendesk_id, ticket["ticket_id"])
            made.append(zendesk_id)
        except Exception:  # noqa: BLE001 - Zendesk being down must not break call logging
            log.exception("Zendesk: could not make a ticket for %s", ticket["ticket_id"])
    return made
