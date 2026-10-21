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
    """Zendesk configured, with requests.post faked. `fail` makes ticket creation return that status."""
    monkeypatch.setattr(config, "ZENDESK_SUBDOMAIN", "acme")
    monkeypatch.setattr(config, "ZENDESK_CLIENT_ID", "client-id")
    monkeypatch.setattr(config, "ZENDESK_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(zendesk, "_token", {"value": "", "expires_at": 0.0})
    state = {"calls": [], "fail": None, "next_id": 9001}

    def post(url, json=None, headers=None, timeout=None):
        state["calls"].append({"url": url, "json": json, "headers": headers or {}})
        if url.endswith("/oauth/tokens"):
            return FakeResponse(200, {"access_token": "tok-1", "token_type": "bearer"})
        if state["fail"]:
            return FakeResponse(state["fail"], {"error": "nope"})
        state["next_id"] += 1
        return FakeResponse(201, {"ticket": {"id": state["next_id"]}})

    monkeypatch.setattr(zendesk.requests, "post", post)
    return state


def test_call_with_a_board_ticket_makes_a_zendesk_ticket(client, tool, zd):
    ticket_id = _ticket(tool)
    assert _post(client, "conv_zd_1").json()["status"] == "ok"

    token_call, ticket_call = zd["calls"]
    assert token_call["url"] == "https://acme.zendesk.com/oauth/tokens"
    assert token_call["json"] == {"grant_type": "client_credentials", "client_id": "client-id",
                                  "client_secret": "client-secret", "scope": "tickets:write users:write"}
    assert ticket_call["url"] == "https://acme.zendesk.com/api/v2/tickets.json"
    assert ticket_call["headers"]["Authorization"] == "Bearer tok-1"
    sent = ticket_call["json"]["ticket"]
    assert sent["tags"] == ["nightagent"] and sent["priority"] == "urgent"
    assert "Priya Shah" in sent["subject"] and "Main entrance won't unlock" in sent["subject"]
    body = sent["comment"]["body"]
    assert "Caller: Priya Shah" in body and "Priority: High priority" in body
    assert "Call summary: Main entrance won't unlock; technician paged." in body
    assert sent["comment"]["public"] is False
    assert "4245550119" not in json.dumps(sent)  # the callback number stays out of Zendesk

    assert get_store().get_ticket(ticket_id)["zendesk_ticket_id"] == 9002


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
    zd["fail"] = 500
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


def test_off_unless_configured(client, tool, zd, monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_CLIENT_SECRET", "")
    _ticket(tool)
    _post(client, "conv_zd_1")
    assert zd["calls"] == []
