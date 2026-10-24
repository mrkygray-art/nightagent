"""Sam on Deepgram: the session, the tool bridge, the end of the call, and how the rest of NightAgent tells the calls apart."""
import json

import pytest

from app import config, deepgram_voice as dg, evaluation, routes_deepgram, scorecard, zendesk
from app.service import public_ticket
from app.store import get_store

TICKET = {"customer_id": "C-1002", "caller_name": "James Carter", "callback_number": "3105550178",
          "issue_summary": "Keypad shows a trouble light since 9 pm", "category": "panel_trouble",
          "suggested_priority": "urgent"}


@pytest.fixture(autouse=True)
def deepgram(monkeypatch):
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "test-deepgram-key")
    monkeypatch.setattr(dg, "grant_token", lambda: "jwt-for-the-browser")
    monkeypatch.setattr(dg, "read_transcript", lambda text: {"summary": "Keypad trouble light at the storage site.",
                                                             "sentiment": "neutral"})
    routes_deepgram._all_calls.clear()
    routes_deepgram._calls_by_ip.clear()
    routes_deepgram._tool_calls.clear()
    routes_deepgram._ended.clear()


def _start(client) -> dict:
    res = client.post("/api/deepgram/session")
    assert res.status_code == 200, res.text
    return res.json()


def _tool(client, session, name, args):
    res = client.post("/api/deepgram/tool", json={"session": session, "name": name, "arguments": json.dumps(args)})
    assert res.status_code == 200, res.text
    return json.loads(res.json()["content"])


def test_settings_use_flux_aura2_and_claude():
    s = dg.settings()
    agent = s["agent"]
    assert agent["listen"]["provider"] == {**agent["listen"]["provider"], "type": "deepgram", "version": "v2",
                                           "model": "flux-general-en"}
    assert 500 <= agent["listen"]["provider"]["eot_timeout_ms"] < 5000  # shorter than Flux's default (Deepgram allows 500-60000)
    assert agent["speak"]["provider"]["model"].startswith("aura-2-") and agent["speak"]["provider"]["version"] == "v1"
    assert agent["think"]["provider"]["type"] == "anthropic"
    assert len(agent["think"]["prompt"]) < 25_000  # Deepgram's limit for managed LLMs
    names = {f["name"] for f in agent["think"]["functions"]}
    assert names == set(routes_deepgram.TOOLS) | {"end_call"}
    # The server fills in conversation_id; the model never sees it
    assert not any("conversation_id" in f["parameters"].get("properties", {}) for f in agent["think"]["functions"])
    assert s["audio"]["input"] == {"encoding": "linear16", "sample_rate": 16000}


def test_prompt_has_no_handoffs():
    prompt = dg.PROMPT.read_text(encoding="utf-8")
    for word in ("transfer_to_agent", "Jordan", "Riley"):
        assert word not in prompt
    assert "end_call" in prompt and "Deepgram" in prompt


def test_session_is_signed_and_expires():
    conv, session = dg.new_session(now=1000)
    assert conv.startswith("dg_")
    assert dg.check_session(session, now=1000) == conv
    assert dg.check_session(session, now=1000 + dg.SESSION_MINUTES * 60 + 1) is None
    head, sig = session.rsplit(".", 1)
    assert dg.check_session(f"{head}.{sig[:-1]}x", now=1000) is None
    other, _ = dg.new_session(now=1000)
    assert dg.check_session(session.replace(conv, other), now=1000) is None
    assert dg.check_session("nonsense", now=1000) is None


def test_session_endpoint(client):
    start = _start(client)
    assert start["token"] == "jwt-for-the-browser"
    assert start["url"] == dg.AGENT_URL
    assert dg.check_session(start["session"])
    assert "test-deepgram-key" not in json.dumps(start)  # the API key never reaches the browser


def test_session_off_without_key(client, monkeypatch):
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "")
    assert client.post("/api/deepgram/session").status_code == 503


def test_session_rate_limit_per_caller(client, monkeypatch):
    monkeypatch.setattr(config, "DEEPGRAM_CALLS_PER_IP_HOUR", 2)
    assert client.post("/api/deepgram/session").status_code == 200
    assert client.post("/api/deepgram/session").status_code == 200
    assert client.post("/api/deepgram/session").status_code == 429


def test_tools_need_a_session(client):
    res = client.post("/api/deepgram/tool", json={"session": "dg_x.1.y", "name": "lookup_customer", "arguments": "{}"})
    assert res.status_code == 401


def test_create_ticket_lands_on_the_board_as_a_deepgram_call(client):
    start = _start(client)
    conv = dg.check_session(start["session"])
    found = _tool(client, start["session"], "lookup_customer", {"query": "310-555-0178"})
    assert found.get("customer") or found.get("matches") or found.get("found") is not False
    made = _tool(client, start["session"], "create_ticket", {**TICKET, "conversation_id": "someone-elses-call"})
    ticket = get_store().get_ticket(made["ticket_id"])
    assert ticket["conversation_id"] == conv  # forced to this call's id
    assert public_ticket(ticket)["voice"] == "deepgram"


def test_unknown_tool_and_bad_arguments(client):
    start = _start(client)
    assert "error" in _tool(client, start["session"], "transfer_to_agent", {})
    res = client.post("/api/deepgram/tool", json={"session": start["session"], "name": "create_ticket", "arguments": "{not json"})
    assert "error" in json.loads(res.json()["content"])
    assert "error" in _tool(client, start["session"], "create_ticket", {"caller_name": "Only a name"})


def test_page_only_for_a_ticket_from_this_call(client):
    mine, other = _start(client), _start(client)
    made = _tool(client, other["session"], "create_ticket", {**TICKET, "category": "active_alarm",
                                                             "suggested_priority": "emergency"})
    reply = _tool(client, mine["session"], "page_on_call_tech", {"ticket_id": made["ticket_id"]})
    assert reply["paged"] is False and "this call" in reply["message"]


def test_tool_calls_are_capped_per_call(client, monkeypatch):
    monkeypatch.setattr(dg, "MAX_TOOL_CALLS", 2)
    start = _start(client)
    for _ in range(2):
        assert "error" not in _tool(client, start["session"], "lookup_customer", {"query": "Westside"})
    assert "error" in _tool(client, start["session"], "lookup_customer", {"query": "Westside"})


def test_end_of_call_stores_and_syncs_once(client, monkeypatch):
    synced = []
    monkeypatch.setattr(zendesk, "sync_call", lambda conv, summary, found: synced.append((conv, summary, found)))
    start = _start(client)
    conv = dg.check_session(start["session"])
    _tool(client, start["session"], "create_ticket", TICKET)
    body = {"session": start["session"], "duration_secs": 95.4,
            "transcript": [{"role": "assistant", "content": "This is Sam."},
                           {"role": "user", "content": "My number is 310 555 0178, the keypad is beeping."}],
            "latencies": [{"total_latency": 1.1, "ttt_latency": 0.6, "tts_latency": 0.2},
                          {"total_latency": 0.9, "ttt_latency": 0.5, "tts_latency": 0.2}]}
    assert client.post("/api/deepgram/end", json=body).json()["status"] == "ok"
    assert client.post("/api/deepgram/end", json=body).json()["status"] == "already saved"
    assert len(synced) == 1 and synced[0][0] == conv
    assert synced[0][1] == "Keypad trouble light at the storage site."
    call = get_store().calls_by_ids([conv])[conv]
    assert call["agent_id"] == "deepgram-sam" and call["duration_secs"] == 95
    assert "555 0178" not in call["transcript"] and "0178" in call["transcript"]  # last four only
    assert call["evaluation"]["metrics"]["latency"]["total_latency"] == {"median": 1.1, "max": 1.1, "n": 2}


def test_deepgram_calls_never_go_to_elevenlabs(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "would-be-used")
    monkeypatch.setattr(evaluation.requests, "get", lambda *a, **k: pytest.fail("asked ElevenLabs about a Deepgram call"))
    assert evaluation.fetch_grade("dg_abc")["status"] == "unavailable"


def test_scorecard_leaves_deepgram_calls_out(client, monkeypatch):
    start = _start(client)
    _tool(client, start["session"], "create_ticket", TICKET)
    seen = []
    monkeypatch.setattr(scorecard, "call_metrics", lambda tickets, tool_calls, calls: seen.append((tickets, tool_calls)) or [])
    monkeypatch.setattr(scorecard, "voice_metrics", lambda voice: [])
    monkeypatch.setitem(scorecard._cache, "data", None)
    scorecard.scorecard(lab={"status": "none"})
    tickets, tool_calls = seen[0]
    assert not any(dg.is_deepgram(t.get("conversation_id")) for t in tickets)
    assert not any(dg.is_deepgram(r.get("conversation_id")) for r in tool_calls)


def test_zendesk_ticket_is_tagged_deepgram():
    ticket = {"ticket_id": "NS-1000", "caller_name": "James Carter", "issue_summary": "Keypad trouble",
              "priority": "urgent", "conversation_id": "dg_123"}
    payload = zendesk.ticket_payload(ticket, "Summary")["ticket"]
    assert "deepgram" in payload["tags"] and "Deepgram" in payload["comment"]["body"]
    eleven = zendesk.ticket_payload({**ticket, "conversation_id": "conv_123"}, "Summary")["ticket"]
    assert "deepgram" not in eleven["tags"]


def test_page_serves(client):
    res = client.get("/deepgram")
    assert res.status_code == 200 and "Flux" in res.text and "/api/deepgram/session" in res.text
