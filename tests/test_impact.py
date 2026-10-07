"""Business Impact metrics come from real records, keep live and synthetic apart, and always reconcile."""
import pytest

from app import config, metrics
from app.store import get_store
from tests.conftest import TOOL_HEADERS


def _impact(client):
    return client.get("/api/impact").json()


def _run_scenario_to_check_in(client, scenario, **outcome):
    s = client.post("/api/demo/scenario", json={"scenario": scenario}).json()
    tid, key = s["ticket"]["ticket_id"], s["demo_key"]
    for _ in range(6):
        client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": key})
    token = client.post("/api/demo/follow-up", json={"ticket_id": tid, "demo_key": key}).json()["dynamic_variables"]["follow_up_token"]
    client.post("/tools/follow-up-outcome", headers=TOOL_HEADERS, json={"follow_up_token": token, **outcome})
    return tid


@pytest.fixture
def busy_demo(client, tool, monkeypatch):
    """A mix of every kind of contact: live and synthetic, each outcome, plus a check-in call."""
    monkeypatch.setattr(config, "FOLLOWUP_AGENT_ID", "agent_test")
    # Live 1: emergency ticket, technician paged -> dispatched
    t = tool("create-ticket", {"customer_id": "C-1001", "caller_name": "Maria", "callback_number": "3105550142",
                               "issue_summary": "Back door will not lock", "category": "door_wont_lock",
                               "conversation_id": "conv_live_1"})
    tool("page-on-call", {"ticket_id": t["ticket_id"]})
    # Live 2: same problem reported again -> joins the paged ticket (repeat contact, dispatched)
    tool("create-ticket", {"customer_id": "C-1001", "caller_name": "Maria", "callback_number": "3105550142",
                           "issue_summary": "Still won't lock", "category": "door_wont_lock",
                           "conversation_id": "conv_live_2"})
    # Live 3: routine ticket -> deferred
    tool("create-ticket", {"caller_name": "A", "callback_number": "3105550100", "issue_summary": "Badge not reading",
                           "category": "access_issue", "conversation_id": "conv_live_3"})
    # Live 4: handed to Jordan -> transferred
    tool("lookup-customer", {"query": "4245550119", "conversation_id": "conv_live_4"})
    tool("billing-lookup", {"customer_id": "C-1003", "conversation_id": "conv_live_4"})
    # Live 5: message for the service manager -> message taken, supervisor escalation
    tool("take-message", {"department": "service_manager", "reason": "Unhappy with last visit",
                          "caller_name": "James Carter", "callback_number": "3105550178", "conversation_id": "conv_live_5"})
    # Live 6: answered on the call -> resolved on the call
    tool("lookup-customer", {"query": "3105550178", "conversation_id": "conv_live_6"})
    # Synthetic: two scenarios, one taken through a check-in call that finds a sales lead
    _run_scenario_to_check_in(client, "expansion", resolution="resolved", sales_interest="New readers")
    client.post("/api/demo/scenario", json={"scenario": "poor_service"})
    return t["ticket_id"]


def test_empty_demo_is_all_zero(client):
    m = _impact(client)
    for view in metrics.VIEWS:
        v = m["views"][view]
        assert v["contacts"] == 0 and sum(v["outcomes"].values()) == 0 and v["containment_rate"] is None
    assert m["live_only"]["acw_minutes"] == 0 and m["live_only"]["aht_seconds"] is None
    assert m["default_view"] == "live"


def test_no_revenue_figures(client, busy_demo):
    def keys(d):
        for k, v in d.items():
            yield k
            if isinstance(v, dict):
                yield from keys(v)
    assert not any("revenue" in k or "value" in k for k in keys(_impact(client)))


def test_outcome_buckets_sum_to_contacts_in_every_view(client, busy_demo):
    m = _impact(client)
    for view in metrics.VIEWS:
        v = m["views"][view]
        assert sum(v["outcomes"].values()) == v["contacts"], view
        assert v["live"] + v["synthetic"] == v["contacts"], view
    assert m["views"]["all"]["contacts"] == m["views"]["live"]["contacts"] + m["views"]["synthetic"]["contacts"]


def test_each_contact_gets_the_right_outcome(client, busy_demo):
    live = _impact(client)["views"]["live"]
    assert live["contacts"] == 6
    assert live["outcomes"] == {"dispatched": 2, "deferred": 1, "transferred": 1,
                                "message_taken": 1, "resolved_on_call": 1}
    assert (live["containment_rate"], live["messages_taken"]) == (17, 1)
    assert live["dispatches"] == 2 and live["deferred"] == 1
    assert live["repeat_contacts"] == 1 and live["transfers"] == 1
    assert live["tickets_created"] == 2  # the repeat call joined the first ticket
    assert live["emergencies"] == 2 and live["supervisor_escalations"] == 1


def test_synthetic_scenarios_stay_out_of_live(client, busy_demo):
    m = _impact(client)
    live, synth = m["views"]["live"], m["views"]["synthetic"]
    assert m["synthetic_scenarios"] == synth["contacts"] == 2
    # The scenario's check-in call, its sales lead, and its task count as synthetic, not live
    assert (synth["follow_up_calls"], synth["confirmed_resolved"], synth["opportunities"]) == (1, 1, 1)
    assert (live["follow_up_calls"], live["confirmed_resolved"], live["opportunities"]) == (0, 0, 0)
    # Scenarios never page anyone
    assert synth["outcomes"]["dispatched"] == 0 and synth["outcomes"]["deferred"] == 2


def test_after_call_work_and_handle_time_are_live_only(client, busy_demo):
    m = _impact(client)
    lo = m["live_only"]
    assert lo["acw_minutes"] == 6 * metrics.MINUTES_PER_INTAKE_CALL  # the scenario's check-in isn't live
    assert lo["aht_seconds"] is None and lo["aht_calls"] == 6  # no durations stored yet: "Collecting"
    get_store().merge_call("conv_live_1", {"duration_secs": 120})
    get_store().merge_call("conv_live_3", {"evaluation": {"metrics": {"duration_s": 60}}})
    lo = _impact(client)["live_only"]
    assert (lo["aht_seconds"], lo["aht_timed"]) == (90, 2)


def test_a_ticket_from_before_tool_tracking_still_counts_as_a_contact(client):
    # Reconciliation bug fixed: a call that made a ticket but left no call_received event or tool-call row
    get_store().create_ticket({"caller_name": "Old", "callback_number": "3105550100", "issue_summary": "x",
                               "category": "other", "priority": "routine", "conversation_id": "conv_old"})
    live = _impact(client)["views"]["live"]
    assert live["contacts"] == 1 and live["tickets_created"] == 1 and live["outcomes"]["deferred"] == 1


def test_check_in_calls_are_not_contacts(client, monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUP_AGENT_ID", "agent_test")
    _run_scenario_to_check_in(client, "problem_returns", resolution="problem_returned")
    synth = _impact(client)["views"]["synthetic"]
    assert synth["contacts"] == 1 and synth["came_back"] == 1 and synth["follow_up_calls"] == 1


def test_source_rule_follows_the_ticket_chain():
    by_id = {"A": {"ticket_id": "A", "scenario": "expansion"}, "B": {"ticket_id": "B", "source_ticket_id": "A"},
             "C": {"ticket_id": "C"}}
    assert metrics.source_of_ticket(by_id["B"], by_id) == metrics.SYNTHETIC
    assert metrics.source_of_ticket(by_id["C"], by_id) == metrics.LIVE


def test_every_tile_has_a_definition(client):
    labels = {d["label"] for d in _impact(client)["definitions"]}
    for tile in ("Contacts handled", "Containment rate", "Messages taken", "Warm transfers",
                 "After-call work (ACW) saved", "Average handle time (AHT)", "Ticket creation rate", "Repeat contacts"):
        assert tile in labels
