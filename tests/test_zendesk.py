"""Zendesk: a ticket per board ticket after the post-call webhook (Zendesk itself is faked here)."""
import hashlib
import hmac
import json
import time

import pytest

from app import config, zendesk
from app.store import get_store


def _post(client, conv, summary="Main entrance won't unlock; technician paged."):
    body = json.dumps({"type": "post_call_transcription", "data": {
        "conversation_id": conv, "agent_id": "agent_sam", "metadata": {"call_duration_secs": 60},
        "transcript": [], "analysis": {"transcript_summary": summary}}}).encode()
    ts = int(time.time())
    sig = f"t={ts},v0=" + hmac.new(b"test-webhook-secret", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/elevenlabs/post-call", content=body, headers={"elevenlabs-signature": sig})


def _ticket(tool, conv="conv_zd_1"):
    made = tool("create-ticket", {"customer_id": "C-1003", "caller_name": "Priya Shah", "callback_number": "4245550119",
                                  "issue_summary": "Main entrance won't unlock", "category": "entry_blocked",
                                  "suggested_priority": "emergency", "conversation_id": conv})
    return made["ticket_id"]


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def zd(monkeypatch):
    """Zendesk configured, with requests.post faked by a small Zendesk that keeps users, organizations,
    memberships and idempotency keys the way the API docs describe. `fail` maps a path ("/tickets.json",
    "/users/create_or_update", ...) to a status to answer with, or to an exception to raise."""
    monkeypatch.setattr(config, "ZENDESK_SUBDOMAIN", "acme")
    monkeypatch.setattr(config, "ZENDESK_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "ZENDESK_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(zendesk, "_token", {"value": "", "expires_at": 0.0, "scope": zendesk.SCOPE})
    state = {"calls": [], "fail": {}, "next_id": 9001, "users": {}, "orgs": {}, "memberships": set(),
             "tickets": [], "keys": {}, "allowed_scopes": None}

    def new_id():
        state["next_id"] += 1
        return state["next_id"]

    def post(url, json=None, headers=None, timeout=None):
        state["calls"].append({"url": url, "json": json, "headers": headers or {}})
        if url.endswith("/oauth/tokens"):
            allowed = state["allowed_scopes"]
            if allowed is not None and not set(json["scope"].split()) <= allowed:
                return FakeResponse(400, {"error": "invalid_scope"})
            return FakeResponse(200, {"access_token": "tok-1", "token_type": "bearer"})
        path = url.removeprefix("https://acme.zendesk.com/api/v2")
        failure = state["fail"].get(path)
        if isinstance(failure, Exception):
            raise failure
        if failure:
            return FakeResponse(failure, {"error": "nope"})
        if path == "/organizations/create_or_update":
            org = json["organization"]
            key = org["external_id"].lower()  # external ids match case-insensitively
            created = key not in state["orgs"]
            if created:
                state["orgs"][key] = {"id": new_id()}
            state["orgs"][key].update(org)
            return FakeResponse(201 if created else 200, {"organization": state["orgs"][key]})
        if path == "/users/create_or_update":
            user = json["user"]
            key = user["external_id"].lower()
            created = key not in state["users"]
            if created:
                state["users"][key] = {"id": new_id(), "organization_id": None}
            state["users"][key].update(user)
            return FakeResponse(201 if created else 200, {"user": state["users"][key]})
        if path == "/organization_memberships":
            m = json["organization_membership"]
            pair = (m["user_id"], m["organization_id"])
            if pair in state["memberships"]:
                return FakeResponse(422, {"error": "already a member"})
            state["memberships"].add(pair)
            for u in state["users"].values():
                if u["id"] == m["user_id"] and not u["organization_id"]:
                    u["organization_id"] = m["organization_id"]  # the first one becomes the default
            return FakeResponse(201, {"organization_membership": {"id": new_id(), **m}})
        if path == "/tickets.json":
            key = (headers or {}).get("Idempotency-Key")
            if key in state["keys"]:
                body, response = state["keys"][key]
                return response if body == json else FakeResponse(400, {"error": "IdempotentRequestError"})
            state["tickets"].append(json["ticket"])
            response = FakeResponse(201, {"ticket": {"id": new_id()}})
            if key:
                state["keys"][key] = (json, response)
            return response
        raise AssertionError(f"unexpected Zendesk call {path}")

    monkeypatch.setattr(zendesk.requests, "post", post)
    return state


def _paths(zd):
    return [c["url"].removeprefix("https://acme.zendesk.com").removeprefix("/api/v2") for c in zd["calls"]]


def test_call_with_a_board_ticket_makes_a_zendesk_ticket(client, tool, zd):
    ticket_id = _ticket(tool)
    assert _post(client, "conv_zd_1").json()["status"] == "ok"

    token_call, ticket_call = zd["calls"][0], zd["calls"][-1]
    assert token_call["url"] == "https://acme.zendesk.com/oauth/tokens"
    assert token_call["json"] == {"grant_type": "client_credentials", "client_id": "client-id",
                                  "client_secret": "client-secret",
                                  "scope": "tickets:write users:write users:read organizations:write"}
    assert ticket_call["url"] == "https://acme.zendesk.com/api/v2/tickets.json"
    assert ticket_call["headers"]["Authorization"] == "Bearer tok-1"
    sent = ticket_call["json"]["ticket"]
    assert sent["tags"] == ["nightagent"] and sent["priority"] == "urgent"
    assert "Priya Shah" in sent["subject"] and "Main entrance won't unlock" in sent["subject"]
    body = sent["comment"]["body"]
    assert "Caller: Priya Shah" in body and "Priority: High priority" in body
    assert "Call summary: Main entrance won't unlock; technician paged." in body
    assert sent["comment"]["public"] is False
    assert "4245550119" not in json.dumps(zd["calls"])  # the callback number stays out of Zendesk

    assert get_store().get_ticket(ticket_id)["zendesk_ticket_id"] == zd["next_id"]


def test_webhook_retry_does_not_make_a_second_zendesk_ticket(client, tool, zd):
    _ticket(tool)
    _post(client, "conv_zd_1")
    _post(client, "conv_zd_1")
    assert sum(c["url"].endswith("/tickets.json") for c in zd["calls"]) == 1


def test_token_is_reused_across_calls(client, tool, zd):
    _ticket(tool, "conv_zd_1")
    _ticket(tool, "conv_zd_2")
    _post(client, "conv_zd_1")
    _post(client, "conv_zd_2")
    assert sum(c["url"].endswith("/oauth/tokens") for c in zd["calls"]) == 1


def test_zendesk_failure_never_breaks_call_logging(client, tool, zd):
    ticket_id = _ticket(tool)
    zd["fail"] = {"/tickets.json": 500}
    assert _post(client, "conv_zd_1").json()["status"] == "ok"
    assert get_store().calls["conv_zd_1"]["eval_status"] == "done"
    assert not get_store().get_ticket(ticket_id).get("zendesk_ticket_id")


def test_zendesk_unreachable_never_breaks_call_logging(client, tool, zd, monkeypatch):
    _ticket(tool)

    def down(*args, **kwargs):
        raise ConnectionError("no route to host")
    monkeypatch.setattr(zendesk.requests, "post", down)
    assert _post(client, "conv_zd_1").json()["status"] == "ok"
    assert get_store().calls["conv_zd_1"]["eval_status"] == "done"


def test_call_without_a_board_ticket_makes_nothing(client, zd):
    assert _post(client, "conv_zd_none").json()["status"] == "ok"
    assert zd["calls"] == []


@pytest.mark.parametrize("value", ["acme", "acme.zendesk.com", "https://acme.zendesk.com/", " ACME.zendesk.com "])
def test_subdomain_accepts_the_full_address_too(monkeypatch, value):
    monkeypatch.setattr(config, "ZENDESK_SUBDOMAIN", value)
    assert zendesk._base_url() == "https://acme.zendesk.com"


def test_off_unless_configured(client, tool, zd, monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_CLIENT_SECRET", "")
    _ticket(tool)
    _post(client, "conv_zd_1")
    assert zd["calls"] == []


# --- Requesters, organizations and custom fields ---------------------------------------------------------

def _make(tool, conv="conv_zd_1", customer_id="C-1003", caller_name="Priya Shah", category="entry_blocked"):
    args = {"caller_name": caller_name, "callback_number": "4245550119", "issue_summary": "Main entrance won't unlock",
            "category": category, "suggested_priority": "emergency", "conversation_id": conv}
    if customer_id:
        args["customer_id"] = customer_id
    return tool("create-ticket", args)["ticket_id"]


@pytest.fixture
def fields(monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_FIELD_NIGHTAGENT_ID", "360001")
    monkeypatch.setattr(config, "ZENDESK_FIELD_CATEGORY", "360002")
    monkeypatch.setattr(config, "ZENDESK_FIELD_CALL_SOURCE", "360003")


def _fail_board_saves(monkeypatch, times=None):
    """Saving the Zendesk id on the board row fails (all the time, or the first `times` tries)."""
    store = get_store()
    real_update = store.update_ticket
    left = {"n": times}

    def update(tid, changes):
        if "zendesk_ticket_id" in changes and (left["n"] is None or left["n"] > 0):
            if left["n"] is not None:
                left["n"] -= 1
            raise RuntimeError("database blip")
        return real_update(tid, changes)
    monkeypatch.setattr(store, "update_ticket", update)


def test_caller_becomes_an_end_user_in_their_account_organization(client, tool, zd, fields):
    ticket_id = _make(tool)
    _post(client, "conv_zd_1")

    assert _paths(zd) == ["/oauth/tokens", "/organizations/create_or_update", "/users/create_or_update",
                          "/organization_memberships", "/tickets.json"]
    org_call, user_call, member_call, ticket_call = zd["calls"][1:]
    assert org_call["json"] == {"organization": {"external_id": "C-1003", "name": "Harbor Logistics Warehouse"}}
    assert user_call["json"] == {"user": {"external_id": "C-1003:priya-shah", "name": "Priya Shah", "role": "end-user"}}
    org_id, user_id = zd["orgs"]["c-1003"]["id"], zd["users"]["c-1003:priya-shah"]["id"]
    assert member_call["json"] == {"organization_membership": {"user_id": user_id, "organization_id": org_id}}

    sent = ticket_call["json"]["ticket"]
    assert sent["requester_id"] == user_id and sent["organization_id"] == org_id
    assert sent["custom_fields"] == [{"id": 360001, "value": ticket_id}, {"id": 360002, "value": "entry_blocked"},
                                     {"id": 360003, "value": "nightagent_phone"}]
    assert ticket_call["headers"]["Idempotency-Key"] == f"nightagent-{ticket_id}"
    # The user is name + external id only (checked exactly above), and the number is in no request at all
    assert "4245550119" not in json.dumps([c["json"] for c in zd["calls"][1:]])


def test_note_is_written_by_the_integration_user_not_the_caller(client, tool, zd, monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_INTEGRATION_USER_ID", "56667084092307")
    _make(tool)
    _post(client, "conv_zd_1")
    sent = zd["tickets"][0]
    assert sent["submitter_id"] == 56667084092307 and sent["requester_id"]


def test_no_submitter_without_an_integration_user_or_a_requester(client, tool, zd, monkeypatch):
    _make(tool, "conv_zd_1")
    _post(client, "conv_zd_1")
    assert "submitter_id" not in zd["tickets"][0]  # setting unset
    monkeypatch.setattr(config, "ZENDESK_INTEGRATION_USER_ID", "56667084092307")
    zd["fail"] = {"/users/create_or_update": 500}
    _make(tool, "conv_zd_2", category="camera_offline")
    _post(client, "conv_zd_2")
    # No requester: the API user is already the author, and the plain payload stays exactly the old one
    assert "submitter_id" not in zd["tickets"][1]


def test_refused_ticket_falls_back_without_the_submitter(client, tool, zd, monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_INTEGRATION_USER_ID", "56667084092307")
    _make(tool)
    real_post = zendesk.requests.post

    def post(url, json=None, headers=None, timeout=None):
        if url.endswith("/tickets.json") and "submitter_id" in json["ticket"]:
            zd["calls"].append({"url": url, "json": json, "headers": headers or {}})
            return FakeResponse(422, {"error": "RecordInvalid"})
        return real_post(url, json=json, headers=headers, timeout=timeout)
    monkeypatch.setattr(zendesk.requests, "post", post)
    _post(client, "conv_zd_1")
    (sent,) = zd["tickets"]
    assert "submitter_id" not in sent and "requester_id" not in sent


def test_caller_who_gave_no_name_is_the_accounts_unknown_caller(client, tool, zd):
    _make(tool, caller_name="not given")
    _post(client, "conv_zd_1")
    user_call = next(c for c in zd["calls"] if c["url"].endswith("/users/create_or_update"))
    assert user_call["json"]["user"] == {"external_id": "C-1003:unknown-caller", "name": "Unknown caller",
                                         "role": "end-user"}
    assert zd["tickets"][0]["organization_id"] == zd["orgs"]["c-1003"]["id"]


def test_caller_without_an_account_is_the_unknown_caller_with_no_organization(client, tool, zd):
    _make(tool, customer_id=None, caller_name="Dana Whitfield")
    _post(client, "conv_zd_1")
    assert "/organizations/create_or_update" not in _paths(zd) and "/organization_memberships" not in _paths(zd)
    assert list(zd["users"]) == ["unknown-caller"]
    assert zd["users"]["unknown-caller"]["name"] == "Unknown caller"
    sent = zd["tickets"][0]
    assert sent["requester_id"] == zd["users"]["unknown-caller"]["id"] and "organization_id" not in sent
    assert "Dana Whitfield" not in json.dumps(zd["users"])  # the name stays on the ticket only


def test_same_caller_again_reuses_the_user_and_skips_the_membership(client, tool, zd):
    _make(tool, "conv_zd_1")
    _post(client, "conv_zd_1")
    _make(tool, "conv_zd_2", category="camera_offline")  # a different problem, so a new board ticket
    _post(client, "conv_zd_2")
    assert len(zd["users"]) == 1 and len(zd["orgs"]) == 1 and len(zd["memberships"]) == 1
    assert _paths(zd).count("/organization_memberships") == 1
    assert len(zd["tickets"]) == 2 and zd["tickets"][0]["requester_id"] == zd["tickets"][1]["requester_id"]


def test_webhook_retry_makes_no_second_user_organization_or_ticket(client, tool, zd, fields):
    _make(tool)
    _post(client, "conv_zd_1")
    _post(client, "conv_zd_1")
    assert len(zd["users"]) == 1 and len(zd["orgs"]) == 1 and len(zd["memberships"]) == 1
    assert len(zd["tickets"]) == 1


def test_retry_after_the_board_save_failed_gets_the_same_ticket_back(client, tool, zd, fields, monkeypatch):
    """Zendesk made the ticket but saving its id on the board row failed: the retry sends the same
    Idempotency-Key and body, so Zendesk answers with the first ticket instead of making another."""
    ticket_id = _make(tool)
    _fail_board_saves(monkeypatch, times=1)
    _post(client, "conv_zd_1")
    assert not get_store().get_ticket(ticket_id).get("zendesk_ticket_id")
    _post(client, "conv_zd_1")
    assert _paths(zd).count("/tickets.json") == 2
    assert len(zd["tickets"]) == 1 and len(zd["users"]) == 1 and len(zd["memberships"]) == 1
    first_id = zd["keys"][f"nightagent-{ticket_id}"][1].json()["ticket"]["id"]
    assert get_store().get_ticket(ticket_id)["zendesk_ticket_id"] == first_id


def test_retry_with_a_different_body_is_refused_not_duplicated(client, tool, zd, fields, monkeypatch):
    """First try: the organization step failed, the ticket was made, saving its id failed. The retry's body
    differs (it now has the organization), so Zendesk refuses the reused key (400). That must not fall
    back to a second, old-way ticket."""
    ticket_id = _make(tool)
    _fail_board_saves(monkeypatch)
    zd["fail"] = {"/organizations/create_or_update": 503}
    _post(client, "conv_zd_1")
    zd["fail"] = {}
    assert _post(client, "conv_zd_1").json()["status"] == "ok"
    assert len(zd["tickets"]) == 1
    assert not any(c["headers"].get("Idempotency-Key", "").endswith("-plain") for c in zd["calls"])
    assert not get_store().get_ticket(ticket_id).get("zendesk_ticket_id")


def test_user_step_failure_still_makes_the_ticket_without_a_requester(client, tool, zd, fields):
    ticket_id = _make(tool)
    zd["fail"] = {"/users/create_or_update": 500}
    assert _post(client, "conv_zd_1").json()["status"] == "ok"
    sent = zd["tickets"][0]
    assert "requester_id" not in sent and "organization_id" not in sent
    assert sent["custom_fields"][0] == {"id": 360001, "value": ticket_id}  # fields don't depend on the user
    assert "/organization_memberships" not in _paths(zd)
    assert get_store().get_ticket(ticket_id)["zendesk_ticket_id"]


def test_user_step_timeout_still_makes_the_ticket(client, tool, zd):
    ticket_id = _make(tool)
    zd["fail"] = {"/users/create_or_update": TimeoutError("read timed out")}
    assert _post(client, "conv_zd_1").json()["status"] == "ok"
    assert "requester_id" not in zd["tickets"][0]
    assert get_store().get_ticket(ticket_id)["zendesk_ticket_id"]


def test_organization_failure_keeps_the_requester_but_no_organization(client, tool, zd):
    _make(tool)
    zd["fail"] = {"/organizations/create_or_update": 422}  # say, a same-named organization without our external id
    _post(client, "conv_zd_1")
    sent = zd["tickets"][0]
    assert sent["requester_id"] == zd["users"]["c-1003:priya-shah"]["id"] and "organization_id" not in sent
    assert "/organization_memberships" not in _paths(zd)


def test_membership_failure_leaves_the_organization_off_the_ticket(client, tool, zd):
    _make(tool)
    zd["fail"] = {"/organization_memberships": 422}
    _post(client, "conv_zd_1")
    sent = zd["tickets"][0]
    assert sent["requester_id"] and "organization_id" not in sent


def test_refused_ticket_is_made_the_old_way(client, tool, zd, fields, monkeypatch):
    """A bad field id or value: Zendesk answers 422 and makes nothing, so the plain ticket goes in instead."""
    ticket_id = _make(tool)
    real_post = zendesk.requests.post

    def post(url, json=None, headers=None, timeout=None):
        if url.endswith("/tickets.json") and "custom_fields" in json["ticket"]:
            zd["calls"].append({"url": url, "json": json, "headers": headers or {}})
            return FakeResponse(422, {"error": "RecordInvalid"})
        return real_post(url, json=json, headers=headers, timeout=timeout)
    monkeypatch.setattr(zendesk.requests, "post", post)

    assert _post(client, "conv_zd_1").json()["status"] == "ok"
    (sent,) = zd["tickets"]
    assert "requester_id" not in sent and "custom_fields" not in sent and "organization_id" not in sent
    assert sent["tags"] == ["nightagent"] and sent["external_id"] == ticket_id
    assert zd["calls"][-1]["headers"]["Idempotency-Key"] == f"nightagent-{ticket_id}-plain"
    assert get_store().get_ticket(ticket_id)["zendesk_ticket_id"]

    _post(client, "conv_zd_1")  # a retry finds the saved id and sends nothing
    assert len(zd["tickets"]) == 1


def test_ticket_server_error_does_not_fall_back(client, tool, zd, fields):
    """A 5xx may still have made the ticket, so no second (old-way) ticket is tried."""
    ticket_id = _make(tool)
    zd["fail"] = {"/tickets.json": 502}
    assert _post(client, "conv_zd_1").json()["status"] == "ok"
    assert _paths(zd).count("/tickets.json") == 1
    assert not get_store().get_ticket(ticket_id).get("zendesk_ticket_id")


def test_client_without_the_organizations_scope_still_makes_tickets(client, tool, zd):
    zd["allowed_scopes"] = {"tickets:write", "users:write"}
    ticket_id = _make(tool)
    _post(client, "conv_zd_1")
    scopes = [c["json"]["scope"] for c in zd["calls"] if c["url"].endswith("/oauth/tokens")]
    assert scopes == ["tickets:write users:write users:read organizations:write", "tickets:write users:write"]
    assert "/organizations/create_or_update" not in _paths(zd)
    sent = zd["tickets"][0]
    assert sent["requester_id"] and "organization_id" not in sent
    assert get_store().get_ticket(ticket_id)["zendesk_ticket_id"]


def test_custom_fields_left_off_when_unset_or_not_a_number(client, tool, zd, monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_FIELD_NIGHTAGENT_ID", "360001")
    monkeypatch.setattr(config, "ZENDESK_FIELD_CATEGORY", "category")  # a name pasted instead of the id
    ticket_id = _make(tool)
    _post(client, "conv_zd_1")
    assert zd["tickets"][0]["custom_fields"] == [{"id": 360001, "value": ticket_id}]


def test_no_fields_and_no_requester_sends_the_old_payload_once(client, tool, zd):
    ticket_id = _make(tool)
    zd["fail"] = {"/users/create_or_update": 500, "/organizations/create_or_update": 500}
    _post(client, "conv_zd_1")
    assert _paths(zd).count("/tickets.json") == 1
    assert zd["tickets"][0] == zendesk.ticket_payload(get_store().get_ticket(ticket_id),
                                                      "Main entrance won't unlock; technician paged.")["ticket"]


@pytest.mark.parametrize("name, expected", [
    ("Priya Shah", "priya-shah"), ("  José   O'Brien ", "jose-o-brien"), ("MARY-ANN smith!", "mary-ann-smith"),
])
def test_slug(name, expected):
    assert zendesk.slug(name) == expected


def test_slug_of_a_name_without_latin_letters_is_a_stable_hash():
    assert zendesk.slug("李伟") == zendesk.slug(" 李伟 ") and zendesk.slug("李伟").startswith("n-")
    assert zendesk.slug("李伟") != zendesk.slug("王芳")
