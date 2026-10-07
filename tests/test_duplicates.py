"""Same caller twice: a second report of an open problem joins the existing ticket."""
from app.store import get_store

GATE = {"customer_id": "C-1002", "caller_name": "James Carter", "callback_number": "3105550178",
        "issue_summary": "Front gate stuck open", "category": "cannot_secure_site", "suggested_priority": "emergency"}


def _ticket(tool, conv, **overrides):
    return tool("create-ticket", {**GATE, "conversation_id": conv, **overrides})


def test_second_report_joins_the_open_ticket_and_does_not_page_again(client, tool):
    first = _ticket(tool, "conv_dup_1")
    tool("page-on-call", {"ticket_id": first["ticket_id"]})
    second = _ticket(tool, "conv_dup_2", caller_name="Dana Carter", issue_summary="Gate still stuck open")
    assert second["ticket_id"] == second["duplicate_of"] == first["ticket_id"]
    assert second["already_alerted"] is True and second["mention_billing"] is False
    assert "Do NOT call page_on_call_tech" in second["next_step"]
    assert len(get_store().tickets) == 1
    events = [e["event_type"] for e in client.get(f"/api/tickets/{first['ticket_id']}").json()["events"]]
    assert events.count("caller_called_again") == 1
    again = tool("page-on-call", {"ticket_id": first["ticket_id"]})
    assert "already paged" in again["message"]


def test_repeat_call_is_on_the_ticket_not_the_phone_only_list(client, tool):
    first = _ticket(tool, "conv_dup_3")
    tool("lookup-customer", {"query": "3105550178", "conversation_id": "conv_dup_4"})
    _ticket(tool, "conv_dup_4")
    assert client.get("/api/calls").json() == []
    live = client.get("/api/impact").json()["views"]["live"]
    assert live["contacts"] == 2 and live["outcomes"]["resolved_on_call"] == 0  # both calls are on the ticket
    assert live["repeat_contacts"] == 1
    assert first["ticket_id"] in {t["ticket_id"] for t in get_store().tickets.values()}


def test_a_different_problem_gets_its_own_ticket(tool):
    first = _ticket(tool, "conv_dup_5")
    other = _ticket(tool, "conv_dup_6", category="system_offline", suggested_priority="urgent",
                    issue_summary="Cameras are down")
    assert other["ticket_id"] != first["ticket_id"] and "duplicate_of" not in other


def test_a_closed_ticket_does_not_absorb_a_new_report(tool):
    first = _ticket(tool, "conv_dup_7")
    get_store().update_ticket(first["ticket_id"], {"status": "closed"})
    assert _ticket(tool, "conv_dup_8")["ticket_id"] != first["ticket_id"]


def test_a_more_serious_second_call_raises_the_priority(client, tool):
    first = _ticket(tool, "conv_dup_9", suggested_priority="routine", category="other",
                    issue_summary="Gate is slow to close")
    assert first["priority"] == "routine"
    second = _ticket(tool, "conv_dup_10", suggested_priority="emergency", category="other",
                     issue_summary="Now the gate won't close at all and the lot is open")
    assert second["duplicate_of"] == first["ticket_id"] and second["priority"] == "emergency"
    assert "call page_on_call_tech now" in second["next_step"]  # never alerted before, so alert now
    assert get_store().get_ticket(first["ticket_id"])["priority"] == "emergency"


def test_without_an_account_the_callback_number_matches(tool):
    plain = {k: v for k, v in GATE.items() if k != "customer_id"}
    first = tool("create-ticket", {**plain, "conversation_id": "conv_dup_11"})
    second = tool("create-ticket", {**plain, "conversation_id": "conv_dup_12"})
    assert second["duplicate_of"] == first["ticket_id"]
    third = tool("create-ticket", {**plain, "callback_number": "2135550100", "conversation_id": "conv_dup_13"})
    assert third["ticket_id"] != first["ticket_id"]


def test_failure_injection_runs_in_a_sandbox(client):
    result = client.post("/api/lab/inject/duplicate-caller").json()
    assert result["passed"] and len(result["checks"]) == 5
    assert get_store().tickets == {} and get_store().tool_calls == []  # the live store was never touched
    assert client.post("/api/lab/inject/nope").status_code == 404


def test_a_real_call_in_demo_mode_still_catches_a_repeat(tool):
    first = _ticket(tool, "conv_dup_14")
    get_store().update_ticket(first["ticket_id"], {"demo": True})  # the caller's page claimed it into Demo Mode
    assert _ticket(tool, "conv_dup_15")["duplicate_of"] == first["ticket_id"]


def test_made_up_scenarios_never_absorb_a_real_call(tool):
    fake = get_store().create_ticket({**GATE, "priority": "emergency", "scenario": "after_hours_emergency"})
    assert _ticket(tool, "conv_dup_16")["ticket_id"] != fake["ticket_id"]


def test_the_board_knows_which_calls_joined_a_ticket(client, tool):
    from app.service import call_ref
    first = _ticket(tool, "conv_dup_17")
    _ticket(tool, "conv_dup_18")
    row = next(t for t in client.get("/api/tickets").json() if t["ticket_id"] == first["ticket_id"])
    assert row["call_ref"] == call_ref("conv_dup_17") and row["call_refs"] == [call_ref("conv_dup_18")]
