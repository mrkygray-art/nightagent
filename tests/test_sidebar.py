"""The Zendesk sidebar endpoint: secret, rate limit, 404 for tickets we didn't make, nothing sensitive out."""
import hashlib
import hmac
import json
import time

import pytest

from app import config, routes_sidebar
from app.store import get_store

SECRET = "test-sidebar-secret-0123456789"
HEADERS = {"x-sidebar-secret": SECRET}
CONV = "conv_sb_1"


@pytest.fixture(autouse=True)
def sidebar_on(monkeypatch):
    monkeypatch.setattr(config, "SIDEBAR_SECRET", SECRET)
    monkeypatch.setattr(config, "SIDEBAR_REQUESTS_PER_MINUTE", 60)
    routes_sidebar._hits.clear()
    yield
    routes_sidebar._hits.clear()


def _webhook(client, conv=CONV):
    turns = [
        {"role": "agent", "message": "NightAgent after-hours line, this is Sam.", "time_in_call_secs": 0,
         "agent_metadata": {"agent_id": config.ELEVENLABS_AGENT_ID}},
        {"role": "user", "message": "My number is 310-555-0142, email maria@example.com. The back door won't lock.",
         "time_in_call_secs": 4},
        {"role": "agent", "message": "", "time_in_call_secs": 9, "agent_metadata": {"agent_id": config.ELEVENLABS_AGENT_ID},
         "tool_calls": [{"tool_name": "lookup_customer"}],
         "tool_results": [{"tool_name": "lookup_customer", "is_error": False, "tool_latency_secs": 0.3}]},
        {"role": "agent", "message": "", "time_in_call_secs": 30, "agent_metadata": {"agent_id": config.ELEVENLABS_AGENT_ID},
         "tool_calls": [{"tool_name": "create_ticket"}],
         "tool_results": [{"tool_name": "create_ticket", "is_error": True, "tool_latency_secs": 8.0}]},
        {"role": "agent", "message": "", "time_in_call_secs": 41, "agent_metadata": {"agent_id": config.ELEVENLABS_AGENT_ID},
         "tool_results": [{"tool_name": "create_ticket", "is_error": False}, {"tool_name": "page_on_call_tech", "is_error": False}]},
        {"role": "agent", "message": "I've read back three one oh five five five oh one four two. Ticket made.",
         "time_in_call_secs": 50, "agent_metadata": {"agent_id": config.ELEVENLABS_AGENT_ID}},
    ]
    body = json.dumps({"type": "post_call_transcription", "data": {
        "conversation_id": conv, "agent_id": config.ELEVENLABS_AGENT_ID, "status": "done",
        "metadata": {"call_duration_secs": 60}, "transcript": turns,
        "analysis": {"transcript_summary": "Maria (callback 3105550142) reported the back door won't lock; tech paged.",
                     "evaluation_criteria_results": {
                         "no_unsupported_promises": {"result": "success", "rationale": "Only gave the tool's window."},
                         "confirmed_details_first": {"result": "success", "rationale": "Read back 310 555 0142 first."}}}}}).encode()
    ts = int(time.time())
    sig = f"t={ts},v0=" + hmac.new(b"test-webhook-secret", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    res = client.post("/webhooks/elevenlabs/post-call", content=body, headers={"elevenlabs-signature": sig})
    assert res.json()["status"] == "ok"


def _our_ticket(tool, conv=CONV, zendesk_id=4321):
    tool("lookup-customer", {"query": "3105550142", "conversation_id": conv})
    t = tool("create-ticket", {"customer_id": "C-1001", "caller_name": "Maria Lopez", "callback_number": "3105550142",
                               "issue_summary": "Back door will not lock", "category": "door_wont_lock",
                               "suggested_priority": "emergency", "conversation_id": conv})
    tool("page-on-call", {"ticket_id": t["ticket_id"]})
    get_store().update_ticket(t["ticket_id"], {"zendesk_ticket_id": zendesk_id})
    return t["ticket_id"]


def test_returns_the_call_for_a_ticket_we_made(client, tool):
    tid = _our_ticket(tool)
    _webhook(client)
    res = client.get("/api/zendesk/tickets/4321", headers=HEADERS)
    assert res.status_code == 200 and res.headers["cache-control"] == "no-store"
    v = res.json()
    assert (v["zendesk_ticket_id"], v["nightagent_ticket_id"], v["caller_name"]) == (4321, tid, "Maria Lopez")
    assert (v["priority"], v["priority_label"]) == ("emergency", "High priority")
    assert v["analysis_status"] == "done"
    assert v["call_summary"].startswith("Maria (callback •••0142) reported")

    # Tool calls in call order, the failed attempt marked as failed
    assert [(t["name"], t["ok"]) for t in v["tool_calls"]] == [
        ("lookup_customer", True), ("create_ticket", False), ("create_ticket", True), ("page_on_call_tech", True)]
    assert [t["seconds_into_call"] for t in v["tool_calls"]] == [9, 30, 41, 41]
    assert {t["agent"] for t in v["tool_calls"]} == {"Sam"} and {t["source"] for t in v["tool_calls"]} == {"elevenlabs"}

    # Call checks, each saying whether rules or the AI judged it
    checks = {c["label"]: c for c in v["call_check"]["checks"]}
    assert checks["Avoided unsupported promises"] == {"label": "Avoided unsupported promises", "status": "pass",
                                                      "detail": "Only gave the tool's window.", "judged_by": "ai"}
    assert checks["Confirmed name and number before acting"]["detail"] == "Read back •••0142 first."
    assert checks["Identified the customer"]["judged_by"] == "rules"
    assert checks["Escalation performed"]["status"] == "pass"

    # Redacted transcript, as speaker lines
    assert v["transcript"][0] == {"speaker": "Agent", "text": "NightAgent after-hours line, this is Sam."}
    assert v["transcript"][1]["speaker"] == "Caller" and "•••0142" in v["transcript"][1]["text"]
    assert "•••0142" in v["transcript"][2]["text"]


def test_nothing_sensitive_leaves(client, tool):
    _our_ticket(tool)
    _webhook(client)
    raw = client.get("/api/zendesk/tickets/4321", headers=HEADERS).text
    for secret_thing in ("3105550142", "310-555-0142", "310 555 0142", "three one oh five five five",
                         "maria@example.com", CONV, SECRET, "test-tool-secret", "test-webhook-secret",
                         "callback_number", "conversation_id", "audio"):
        assert secret_thing not in raw, secret_thing


def test_before_the_analysis_arrives_it_uses_our_tool_log(client, tool):
    _our_ticket(tool)
    v = client.get("/api/zendesk/tickets/4321", headers=HEADERS).json()
    assert v["analysis_status"] == "pending" and v["call_summary"] is None and v["transcript"] == []
    assert [t["name"] for t in v["tool_calls"]] == ["lookup_customer", "create_ticket", "page_on_call_tech"]
    assert all(t["ok"] and t["called_at"] and t["source"] == "nightagent_log" for t in v["tool_calls"])
    ai = [c for c in v["call_check"]["checks"] if c["judged_by"] == "ai"]
    assert ai and all(c["status"] == "pending" for c in ai)


def test_never_asks_elevenlabs(client, tool, monkeypatch):
    from app import evaluation
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "would-be-key")

    def no_network(*args, **kwargs):
        raise AssertionError("the sidebar must not call ElevenLabs")
    monkeypatch.setattr(evaluation.requests, "get", no_network)
    _our_ticket(tool)
    assert client.get("/api/zendesk/tickets/4321", headers=HEADERS).status_code == 200


def test_404_for_a_zendesk_ticket_we_did_not_make(client, tool):
    _our_ticket(tool)
    assert client.get("/api/zendesk/tickets/999", headers=HEADERS).status_code == 404


def test_404_for_a_demo_scenario_even_with_a_zendesk_id(client):
    tid = client.post("/api/demo/scenario", json={"scenario": "emergency_resolved"}).json()["ticket"]["ticket_id"]
    get_store().update_ticket(tid, {"zendesk_ticket_id": 777})
    assert client.get("/api/zendesk/tickets/777", headers=HEADERS).status_code == 404


@pytest.mark.parametrize("headers", [{}, {"x-sidebar-secret": "wrong"}, {"x-sidebar-secret": SECRET + "x"},
                                     {"x-tool-secret": "test-tool-secret"}])
def test_needs_the_sidebar_secret(client, tool, headers):
    _our_ticket(tool)
    assert client.get("/api/zendesk/tickets/4321", headers=headers).status_code == 401
    # Without the secret, a ticket we didn't make looks the same as one we did
    assert client.get("/api/zendesk/tickets/999", headers=headers).status_code == 401


def test_secret_is_compared_in_constant_time(client, tool, monkeypatch):
    _our_ticket(tool)  # before the spy, since the tool endpoints compare their own secret
    seen = []
    real = routes_sidebar.hmac.compare_digest
    monkeypatch.setattr(routes_sidebar.hmac, "compare_digest", lambda a, b: seen.append((a, b)) or real(a, b))
    client.get("/api/zendesk/tickets/4321", headers=HEADERS)
    assert seen == [(SECRET.encode(), SECRET.encode())]


def test_off_until_the_secret_is_set(client, tool, monkeypatch):
    monkeypatch.setattr(config, "SIDEBAR_SECRET", "")
    _our_ticket(tool)
    for headers in ({}, {"x-sidebar-secret": ""}, HEADERS):
        assert client.get("/api/zendesk/tickets/4321", headers=headers).status_code == 503


def test_rate_limited_and_guesses_count(client, tool, monkeypatch):
    monkeypatch.setattr(config, "SIDEBAR_REQUESTS_PER_MINUTE", 3)
    _our_ticket(tool)
    for _ in range(3):
        client.get("/api/zendesk/tickets/4321", headers={"x-sidebar-secret": "guess"})
    res = client.get("/api/zendesk/tickets/4321", headers=HEADERS)
    assert res.status_code == 429 and res.headers["retry-after"] == "60"
    # Another client has its own allowance
    other = client.get("/api/zendesk/tickets/4321", headers={**HEADERS, "x-forwarded-for": "203.0.113.9"})
    assert other.status_code == 200


def test_limit_window_slides(client, tool, monkeypatch):
    monkeypatch.setattr(config, "SIDEBAR_REQUESTS_PER_MINUTE", 1)
    clock = [1000.0]
    monkeypatch.setattr(routes_sidebar.time, "time", lambda: clock[0])
    _our_ticket(tool)
    assert client.get("/api/zendesk/tickets/4321", headers=HEADERS).status_code == 200
    assert client.get("/api/zendesk/tickets/4321", headers=HEADERS).status_code == 429
    clock[0] += 61
    assert client.get("/api/zendesk/tickets/4321", headers=HEADERS).status_code == 200


@pytest.mark.parametrize("bad", ["0", "-5", "abc", "1.5", str(2**53 + 1)])
def test_rejects_ids_that_are_not_ticket_numbers(client, bad):
    assert client.get(f"/api/zendesk/tickets/{bad}", headers=HEADERS).status_code == 422


def test_read_only(client, tool):
    _our_ticket(tool)
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/zendesk/tickets/4321", headers=HEADERS).status_code == 405
