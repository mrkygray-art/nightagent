"""Behavior the live demo already depends on: triage rules, the three tools, webhook security."""
import hashlib
import hmac
import json
import time

from app.security import verify_elevenlabs_signature
from app.triage import triage


# ---------- triage rules ----------

def test_policy_sets_emergency_for_unsecured_site():
    assert triage("cannot_secure_site", "routine")[1] == "emergency"


def test_model_can_escalate_but_never_downgrade():
    assert triage("access_issue", "urgent")[1] == "urgent"
    assert triage("active_alarm", "routine")[1] == "emergency"


def test_aliases_and_unknown_categories():
    assert triage("door wont lock", None)[:2] == ("cannot_secure_site", "emergency")
    assert triage("gate-stuck-open", None)[:2] == ("cannot_secure_site", "emergency")
    assert triage("something odd", "nonsense")[:2] == ("other", "routine")


# ---------- tools ----------

def test_tools_require_the_shared_secret(client):
    assert client.post("/tools/lookup-customer", json={"query": "x"}).status_code == 401
    bad = client.post("/tools/lookup-customer", json={"query": "x"}, headers={"x-tool-secret": "nope"})
    assert bad.status_code == 401


def test_lookup_by_phone_and_name(tool):
    assert tool("lookup-customer", {"query": "(310) 555-0142"})["customer"]["customer_id"] == "C-1001"
    assert tool("lookup-customer", {"query": "harbor"})["customer"]["customer_id"] == "C-1003"
    assert tool("lookup-customer", {"query": "nobody here"})["found"] is False


def test_create_ticket_applies_rules_and_speaks_digits(tool):
    out = tool("create-ticket", {
        "customer_id": "C-1001", "caller_name": "Maria", "callback_number": "+1 310 555 0142",
        "issue_summary": "Back door will not lock", "category": "door_wont_lock",
        "suggested_priority": "routine", "conversation_id": "conv_1",
    })
    assert out["priority"] == "emergency"
    assert out["ticket_number_spoken"] == "N S " + " ".join(out["ticket_id"].split("-")[1])
    assert "page_on_call_tech" in out["next_step"]


def test_paging_only_for_emergencies_and_only_once(tool):
    routine = tool("create-ticket", {"caller_name": "A", "callback_number": "1", "issue_summary": "badge",
                                     "category": "badge"})
    assert tool("page-on-call", {"ticket_id": routine["ticket_id"]})["paged"] is False
    emergency = tool("create-ticket", {"caller_name": "B", "callback_number": "2", "issue_summary": "alarm",
                                       "category": "alarm"})
    first = tool("page-on-call", {"ticket_id": emergency["ticket_id"].lower()})
    assert first["paged"] is True and first["simulated"] is True
    assert "already" in tool("page-on-call", {"ticket_id": emergency["ticket_id"]})["message"]


def test_public_ticket_feed_masks_phone_numbers(tool, client):
    tool("create-ticket", {"caller_name": "C", "callback_number": "3105550142", "issue_summary": "x"})
    row = client.get("/api/tickets").json()[0]
    assert row["callback_number"].endswith("0142") and "310" not in row["callback_number"]


# ---------- webhook signatures ----------

def _sign(body: bytes, secret: str, ts: int) -> str:
    return f"t={ts},v0=" + hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()


def test_signature_accepts_valid_rejects_stale_and_wrong():
    body, now = b'{"a":1}', int(time.time())
    assert verify_elevenlabs_signature(body, _sign(body, "s", now), "s", now=now)
    assert not verify_elevenlabs_signature(body, _sign(body, "s", now - 3600), "s", now=now)
    assert not verify_elevenlabs_signature(body, _sign(body, "other", now), "s", now=now)
    two = _sign(body, "old", now) + "," + _sign(body, "s", now).split(",")[1]
    assert verify_elevenlabs_signature(body, two, "s", now=now)  # rotation: either signature works


def test_webhook_rejects_unsigned_and_stores_signed(client):
    event = {"type": "post_call_transcription", "data": {
        "conversation_id": "conv_9", "analysis": {"transcript_summary": "Door fixed."},
        "transcript": [{"role": "agent", "message": "Hi"}, {"role": "user", "message": ""}]}}
    body = json.dumps(event).encode()
    assert client.post("/webhooks/elevenlabs/post-call", content=body).status_code == 401
    ok = client.post("/webhooks/elevenlabs/post-call", content=body, headers={
        "elevenlabs-signature": _sign(body, "test-webhook-secret", int(time.time()))})
    assert ok.status_code == 200 and ok.json()["status"] == "ok"
