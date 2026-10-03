"""Phase 4: Business Impact metrics come from real records and never include revenue."""
from app import config, routes_impact
from tests.conftest import TOOL_HEADERS


def _fresh(client):
    return client.get("/api/impact").json()


def test_empty_demo_is_all_zero(client):
    m = _fresh(client)
    assert m["calls_handled"] == 0 and m["minutes_saved"] == 0
    assert not any("revenue" in k or "value" in k for k in m)


def test_metrics_follow_the_lifecycle(client, tool, monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUP_AGENT_ID", "agent_test")
    # One live call that pages a technician
    t = tool("create-ticket", {"customer_id": "C-1001", "caller_name": "Maria", "callback_number": "3105550142",
                               "issue_summary": "Back door will not lock", "category": "door_wont_lock",
                               "conversation_id": "conv_impact_1"})
    tool("page-on-call", {"ticket_id": t["ticket_id"]})
    # One scenario taken through a follow-up that finds a sales lead
    s = client.post("/api/demo/scenario", json={"scenario": "expansion"}).json()
    tid, key = s["ticket"]["ticket_id"], s["demo_key"]
    for _ in range(6):
        client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": key})
    token = client.post("/api/demo/follow-up", json={"ticket_id": tid, "demo_key": key}).json()["dynamic_variables"]["follow_up_token"]
    client.post("/tools/follow-up-outcome", headers=TOOL_HEADERS, json={
        "follow_up_token": token, "resolution": "resolved", "sales_interest": "New readers"})

    m = _fresh(client)
    assert (m["calls_handled"], m["live_calls"], m["scenario_calls"]) == (2, 1, 1)
    assert m["tickets"] == 2 and m["emergencies"] == 1
    assert m["needed_a_person"] == 1 and m["handled_without_waking_anyone"] == 1
    assert (m["follow_ups"], m["resolved"], m["opportunities"]) == (1, 1, 1)
    # Time saved counts only the real live call and the follow-up, not the simulated scenario call
    assert m["minutes_saved"] == routes_impact.MINUTES_PER_INTAKE_CALL + routes_impact.MINUTES_PER_FOLLOW_UP


def test_calls_without_a_ticket_and_handoffs_are_counted(client, tool):
    before = client.get("/api/impact").json()
    tool("lookup-customer", {"query": "4245550119", "conversation_id": "conv_imp_bill"})
    tool("billing-lookup", {"customer_id": "C-1003", "conversation_id": "conv_imp_bill"})       # handed to Jordan
    tool("lookup-customer", {"query": "3105550178", "conversation_id": "conv_imp_msg"})
    tool("take-message", {"department": "support", "reason": "How do I add a user?", "caller_name": "James Carter",
                          "callback_number": "3105550178", "conversation_id": "conv_imp_msg"})  # a message
    tool("create-ticket", {"caller_name": "A", "callback_number": "3105550100", "issue_summary": "Keypad beeping",
                           "category": "panel_trouble", "conversation_id": "conv_imp_ticket"})  # a ticket
    after = client.get("/api/impact").json()
    assert after["calls_without_ticket"] - before["calls_without_ticket"] == 2
    assert after["specialist_calls"] - before["specialist_calls"] == 1
    assert after["live_calls"] - before["live_calls"] == 3  # every real call, each counted once
