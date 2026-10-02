"""Phase 1: ticket lifecycle, event history, and Demo Mode guards."""
import pytest

from app import lifecycle
from app.store import get_store


# ---------- the state machine ----------

def test_every_state_has_a_label_and_transition_entry():
    assert set(lifecycle.STATES) == set(lifecycle.TRANSITIONS) == set(lifecycle.STATE_LABELS)
    for targets in lifecycle.TRANSITIONS.values():
        assert targets <= set(lifecycle.STATES)


def test_no_skipping_steps():
    assert lifecycle.can_transition("awaiting_dispatch", "technician_assigned")
    assert not lifecycle.can_transition("awaiting_dispatch", "closed")
    assert not lifecycle.can_transition("en_route", "work_completed")
    with pytest.raises(lifecycle.TransitionError):
        lifecycle.check_transition("new", "resolved")


def test_legacy_open_status_reads_as_awaiting_dispatch():
    assert lifecycle.normalize_state("open") == "awaiting_dispatch"
    assert lifecycle.can_transition("open", "dispatched")


def test_demo_path_walks_from_dispatch_to_follow_up_using_allowed_moves():
    state, seen = "awaiting_dispatch", []
    while (step := lifecycle.next_demo_step(state)):
        assert lifecycle.can_transition(state, step[0])
        state = step[0]
        seen.append(state)
    assert seen[-1] == "follow_up_pending" and "work_completed" in seen


# ---------- a live call writes history ----------

def _live_ticket(tool, category="door_wont_lock", conv="conv_live_123456"):
    return tool("create-ticket", {
        "customer_id": "C-1001", "caller_name": "Maria", "callback_number": "3105550142",
        "issue_summary": "Back door will not lock", "category": category, "conversation_id": conv,
    })


def test_call_creates_ticket_awaiting_dispatch_with_three_events(tool, client):
    t = _live_ticket(tool)
    detail = client.get(f"/api/tickets/{t['ticket_id']}").json()
    assert detail["ticket"]["status"] == "awaiting_dispatch"
    assert [e["event_type"] for e in detail["events"]] == ["call_received", "triage_completed", "ticket_created"]
    assert not any(e["simulated"] for e in detail["events"])
    assert "not the AI" in detail["events"][1]["description"]


def test_paging_moves_to_dispatched_and_marks_simulated_page(tool, client):
    t = _live_ticket(tool)
    tool("page-on-call", {"ticket_id": t["ticket_id"]})
    detail = client.get(f"/api/tickets/{t['ticket_id']}").json()
    assert detail["ticket"]["status"] == "dispatched"
    paged = detail["events"][-1]
    assert paged["event_type"] == "technician_paged" and paged["simulated"] is True


def test_history_write_failure_never_breaks_a_call(tool, monkeypatch):
    def boom(_):
        raise RuntimeError("events table missing")
    monkeypatch.setattr(get_store(), "add_event", boom)
    assert _live_ticket(tool)["ticket_id"].startswith("NS-")


def test_public_feed_hides_conversation_ids_and_keys(tool, client):
    _live_ticket(tool)
    client.post("/api/demo/scenario", json={"scenario": "expansion"})
    for row in client.get("/api/tickets").json():
        assert "conversation_id" not in row and "demo_key_hash" not in row
    mine = [r for r in client.get("/api/tickets").json() if r["call_ref"]]
    assert len(mine) == 1 and len(mine[0]["call_ref"]) == 16


# ---------- Demo Mode ----------

def _start(client, scenario="emergency_resolved"):
    res = client.post("/api/demo/scenario", json={"scenario": scenario})
    assert res.status_code == 200, res.text
    return res.json()


def test_scenarios_use_the_priority_rules(client):
    assert {s["id"] for s in client.get("/api/demo/scenarios").json()} == {
        "emergency_resolved", "problem_returns", "expansion", "poor_service"}
    got = {name: _start(client, name)["ticket"]["priority"] for name in
           ("emergency_resolved", "problem_returns", "expansion", "poor_service")}
    assert got == {"emergency_resolved": "emergency", "problem_returns": "emergency",
                   "expansion": "routine", "poor_service": "urgent"}


def test_scenario_events_are_all_labeled_simulated(client):
    started = _start(client)
    assert started["ticket"]["demo"] is True
    assert all(e["simulated"] for e in started["events"])


def test_advance_walks_the_full_path_then_stops(client):
    started = _start(client)
    key, tid = started["demo_key"], started["ticket"]["ticket_id"]
    statuses = []
    for _ in range(6):
        res = client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": key})
        assert res.status_code == 200, res.text
        statuses.append(res.json()["ticket"]["status"])
    assert statuses == ["dispatched", "technician_assigned", "en_route", "onsite",
                        "work_completed", "follow_up_pending"]
    final = res.json()
    assert final["ticket"]["technician_name"] == "Mike Rodriguez"
    assert "fictional" in [e for e in final["events"] if e["event_type"] == "technician_assigned"][0]["description"]
    times = [e["occurred_at"] for e in final["events"]]
    assert times == sorted(times)  # demo clock only moves forward
    assert final["next_step"] is None
    assert client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": key}).status_code == 409


def test_advance_needs_the_right_key(client, tool):
    started = _start(client)
    tid = started["ticket"]["ticket_id"]
    assert client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": "x" * 32}).status_code == 403
    live = _live_ticket(tool)  # a real call's ticket that nobody claimed
    assert client.post("/api/demo/advance", json={"ticket_id": live["ticket_id"],
                                                  "demo_key": started["demo_key"]}).status_code == 403


def test_reset_removes_only_demo_steps(client):
    started = _start(client)
    key, tid = started["demo_key"], started["ticket"]["ticket_id"]
    for _ in range(3):
        client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": key})
    after = client.post("/api/demo/reset", json={"ticket_id": tid, "demo_key": key}).json()
    assert after["ticket"]["status"] == "awaiting_dispatch"
    assert after["ticket"]["technician_name"] is None
    assert [e["event_type"] for e in after["events"]] == ["call_received", "triage_completed", "ticket_created"]


def test_claim_your_own_call_once(client, tool):
    live = _live_ticket(tool, conv="conv_mine_abcdef")
    tid = live["ticket_id"]
    wrong = client.post("/api/demo/claim", json={"ticket_id": tid, "conversation_id": "conv_other_xyz"})
    assert wrong.status_code == 403
    ok = client.post("/api/demo/claim", json={"ticket_id": tid, "conversation_id": "conv_mine_abcdef"})
    assert ok.status_code == 200 and ok.json()["ticket"]["demo"] is True
    again = client.post("/api/demo/claim", json={"ticket_id": tid, "conversation_id": "conv_mine_abcdef"})
    assert again.status_code == 409
    adv = client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": ok.json()["demo_key"]})
    assert adv.json()["ticket"]["status"] == "dispatched"
    # Reset puts a claimed call back where the call left it, keeping the real call events
    back = client.post("/api/demo/reset", json={"ticket_id": tid, "demo_key": ok.json()["demo_key"]}).json()
    assert back["ticket"]["status"] == "awaiting_dispatch" and len(back["events"]) == 3


def test_paged_call_assigns_the_technician_who_was_paged(client, tool):
    from app import config
    live = _live_ticket(tool, conv="conv_paged_abcdef")
    tool("page-on-call", {"ticket_id": live["ticket_id"]})
    key = client.post("/api/demo/claim", json={"ticket_id": live["ticket_id"],
                                               "conversation_id": "conv_paged_abcdef"}).json()["demo_key"]
    out = client.post("/api/demo/advance", json={"ticket_id": live["ticket_id"], "demo_key": key}).json()
    assert out["ticket"]["status"] == "technician_assigned"
    assert out["ticket"]["technician_name"] == config.ONCALL_TECH_NAME
    assert "fictional" not in out["events"][-1]["description"]


def test_scenario_rate_limit(client, monkeypatch):
    from app import demo
    monkeypatch.setattr(demo, "SCENARIOS_PER_HOUR", 2)
    _start(client)
    _start(client)
    assert client.post("/api/demo/scenario", json={"scenario": "expansion"}).status_code == 429


def test_unknown_scenario_and_ticket(client):
    assert client.post("/api/demo/scenario", json={"scenario": "nope"}).status_code == 404
    assert client.get("/api/tickets/NS-0000").status_code == 404
