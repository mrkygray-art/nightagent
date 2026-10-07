"""The ticket view's handoff sections: only stored data, masked phones, no live callers' words."""
from app import config
from app.store import get_store
from tests.conftest import TOOL_HEADERS


def _live_emergency(tool, conv="conv_tv_1"):
    tool("lookup-customer", {"query": "3105550142", "conversation_id": conv})
    t = tool("create-ticket", {"customer_id": "C-1001", "caller_name": "Maria", "callback_number": "3105550142",
                               "issue_summary": "Back door will not lock", "category": "door_wont_lock",
                               "conversation_id": conv})
    tool("page-on-call", {"ticket_id": t["ticket_id"]})
    return t["ticket_id"]


def test_dispatched_live_ticket(client, tool):
    tid = _live_emergency(tool)
    v = client.get(f"/api/tickets/{tid}").json()["view"]
    assert (v["source"], v["outcome"]) == ("live", "dispatched")
    assert v["summary"]["status"] == "pending"  # no post-call summary stored yet
    assert v["intent"]["escalation"][0]["kind"] == "emergency_rule"
    assert v["identity"] == {"status": "not_captured"} and v["actions_status"] == "ok"
    assert v["account"]["phone"].endswith("0142") and "3105550142" not in str(v)
    assert v["whisper"] is None and v["transcript"] is None
    # Handoff context: account and actions present; summary, transcript, identity not stored
    assert (v["handoff"]["count"], v["handoff"]["total"]) == (2, 5)


def test_handoff_context_follows_the_stored_fields(client, tool):
    tid = _live_emergency(tool, "conv_tv_2")
    get_store().merge_call("conv_tv_2", {"summary": "Back door won't lock; tech paged.", "transcript": "Agent: Hi"})
    v = client.get(f"/api/tickets/{tid}").json()["view"]
    assert v["handoff"]["count"] == 4 and v["summary"]["status"] == "ok"
    assert v["transcript"] is None  # a live caller's words never reach the public page


def test_deferred_ticket_has_no_handoff_indicator(client, tool):
    t = tool("create-ticket", {"caller_name": "A", "callback_number": "3105550100", "issue_summary": "Badge",
                               "category": "access_issue", "conversation_id": "conv_tv_3"})
    v = client.get(f"/api/tickets/{t['ticket_id']}").json()["view"]
    assert v["outcome"] == "deferred" and v["handoff"] is None
    assert v["intent"]["escalation"] == [] and v["account"] is None


def test_scenario_ticket_is_synthetic_and_says_there_was_no_call(client, monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUP_AGENT_ID", "agent_test")
    s = client.post("/api/demo/scenario", json={"scenario": "emergency_resolved"}).json()
    v = s["view"]
    assert v["source"] == "synthetic" and v["summary"]["status"] == "no_call" and v["actions_status"] == "no_call"
    tid, key = s["ticket"]["ticket_id"], s["demo_key"]
    for _ in range(6):
        client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": key})
    token = client.post("/api/demo/follow-up", json={"ticket_id": tid, "demo_key": key}).json()["dynamic_variables"]["follow_up_token"]
    client.post("/tools/follow-up-outcome", headers=TOOL_HEADERS, json={
        "follow_up_token": token, "resolution": "resolved", "satisfaction": 5, "customer_comments": "All good now"})
    fu = client.get(f"/api/tickets/{tid}").json()["view"]["follow_up"]
    assert fu["check_in"] == {"result": "Customer said it's fixed", "csat": 5, "words": "All good now"}


def test_transferred_call_shows_whisper_not_captured(client, tool):
    tool("billing-lookup", {"customer_id": "C-1001", "conversation_id": "conv_tv_5"})
    t = tool("create-ticket", {"customer_id": "C-1001", "caller_name": "Maria", "callback_number": "3105550142",
                               "issue_summary": "Keypad beeping", "category": "panel_trouble",
                               "conversation_id": "conv_tv_5"})
    v = client.get(f"/api/tickets/{t['ticket_id']}").json()["view"]
    assert v["transferred"] and v["whisper"] == {"status": "not_captured"} and v["handoff"] is not None
    assert v["intent"]["specialists"] == ["Jordan (billing assistant)"]
