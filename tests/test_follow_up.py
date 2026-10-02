"""Phase 2: NightAgent's follow-up call and the routing rules behind it."""
import pytest

from app import config
from tests.conftest import TOOL_HEADERS


@pytest.fixture(autouse=True)
def follow_up_agent(monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUP_AGENT_ID", "agent_followup_test")


def _ready(client, scenario="emergency_resolved"):
    """A scenario ticket advanced to follow_up_pending, plus the started follow-up."""
    started = client.post("/api/demo/scenario", json={"scenario": scenario}).json()
    tid, key = started["ticket"]["ticket_id"], started["demo_key"]
    for _ in range(6):
        client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": key})
    fu = client.post("/api/demo/follow-up", json={"ticket_id": tid, "demo_key": key})
    assert fu.status_code == 200, fu.text
    return tid, key, fu.json()


def _report(client, token, **fields):
    res = client.post("/tools/follow-up-outcome", headers=TOOL_HEADERS,
                      json={"follow_up_token": token, "conversation_id": "conv_fu_1", **fields})
    assert res.status_code == 200, res.text
    return res.json()


def _detail(client, tid):
    return client.get(f"/api/tickets/{tid}").json()


# ---------- starting the follow-up ----------

def test_follow_up_hands_over_ticket_context_without_private_details(client):
    tid, _, fu = _ready(client)
    v = fu["dynamic_variables"]
    assert fu["agent_id"] == "agent_followup_test"
    assert v["ticket_id"] == tid and v["customer_first_name"] == "Priya"
    assert v["technician_name"] == "Mike Rodriguez" and "entrance" in v["original_issue"]
    assert len(v["follow_up_token"]) > 20
    assert not any("555" in str(x) for x in v.values())  # no phone numbers
    assert _detail(client, tid)["events"][-1]["event_type"] == "follow_up_started"


def test_follow_up_needs_the_key_and_a_finished_job(client):
    started = client.post("/api/demo/scenario", json={"scenario": "expansion"}).json()
    tid, key = started["ticket"]["ticket_id"], started["demo_key"]
    assert client.post("/api/demo/follow-up", json={"ticket_id": tid, "demo_key": key}).status_code == 409
    assert client.post("/api/demo/follow-up", json={"ticket_id": tid, "demo_key": "y" * 32}).status_code == 403


def test_follow_up_off_until_agent_configured(client, monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUP_AGENT_ID", "")
    started = client.post("/api/demo/scenario", json={"scenario": "expansion"}).json()
    tid, key = started["ticket"]["ticket_id"], started["demo_key"]
    for _ in range(6):
        client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": key})
    assert client.post("/api/demo/follow-up", json={"ticket_id": tid, "demo_key": key}).status_code == 503


def test_outcome_tool_requires_tool_secret_and_valid_pass(client):
    _, _, fu = _ready(client)
    no_secret = client.post("/tools/follow-up-outcome", json={"follow_up_token": "x", "resolution": "resolved"})
    assert no_secret.status_code == 401
    assert _report(client, "not-a-real-pass", resolution="resolved")["recorded"] is False


def test_pass_is_single_use(client):
    tid, _, fu = _ready(client)
    token = fu["dynamic_variables"]["follow_up_token"]
    assert _report(client, token, resolution="resolved")["recorded"] is True
    assert _report(client, token, resolution="never_fixed")["recorded"] is False
    assert _detail(client, tid)["ticket"]["status"] == "closed"


# ---------- outcomes ----------

def test_a_resolved_closes_with_csat(client):
    tid, _, fu = _ready(client)
    out = _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="resolved",
                  satisfaction=5, customer_comments="Everything is working great now.")
    assert "closed" in out["tell_the_customer"]
    d = _detail(client, tid)
    assert d["ticket"]["status"] == "closed" and d["ticket"]["csat"] == 5
    types = [e["event_type"] for e in d["events"]]
    assert types[-4:] == ["follow_up_completed", "csat_recorded", "resolution_confirmed", "ticket_closed"]
    real = {"follow_up_started", "follow_up_completed", "csat_recorded", "resolution_confirmed", "ticket_closed"}
    assert not any(e["simulated"] for e in d["events"] if e["event_type"] in real)  # the customer really said it
    times = [e["occurred_at"] for e in d["events"]]
    assert times == sorted(times)  # follow-up events land after the demo-clock steps
    assert d["actions"]["tasks"] == []


def test_b_problem_returned_reopens_and_re_triages(client):
    tid, _, fu = _ready(client, "problem_returns")
    _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="problem_returned",
            current_category="access_issue", current_impact="Door locks but sometimes needs a second try",
            customer_comments="The back door stopped locking right again.")
    d = _detail(client, tid)
    assert d["ticket"]["status"] == "reopened"
    assert d["ticket"]["priority"] == "routine"  # re-evaluated from today's impact, not copied
    assert any(e["event_type"] == "priority_reviewed" for e in d["events"])
    task = d["actions"]["tasks"][0]
    assert task["destination"] == "service" and task["priority"] == "high"


def test_c_never_fixed_escalates_to_service_manager(client):
    tid, _, fu = _ready(client, "poor_service")
    out = _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="never_fixed",
                  satisfaction=1, customer_comments="It never really worked after the tech left.")
    d = _detail(client, tid)
    assert d["ticket"]["status"] == "escalated" and "service manager" in out["tell_the_customer"]
    assert d["actions"]["tasks"][0]["destination"] == "service_manager"
    assert "fictional" in d["actions"]["tasks"][0]["assigned_to"]


def test_d_new_issue_opens_linked_ticket_owned_by_same_browser(client):
    tid, key, fu = _ready(client)
    _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="resolved",
            new_issue_summary="A badge reader at the side door isn't reading badges.", new_issue_category="badge")
    d = _detail(client, tid)
    assert d["ticket"]["status"] == "closed"  # original stays resolved
    new = d["actions"]["tickets"][0]
    assert new["source_ticket_id"] == tid and new["priority"] == "routine"
    assert client.post("/api/demo/advance", json={"ticket_id": new["ticket_id"], "demo_key": key}).status_code == 200


def test_e_sales_interest_creates_opportunity_with_no_invented_value(client):
    tid, _, fu = _ready(client, "expansion")
    _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="resolved",
            sales_interest="Replace readers building-wide with mobile credentials",
            sales_scope="About 14 doors", sales_device_count="14", sales_timeline="3 to 6 months")
    d = _detail(client, tid)
    opp = d["actions"]["opportunities"][0]
    assert opp["opportunity_id"].startswith("OPP-") and opp["estimated_value"].startswith("TBD")
    assert "Sarah Johnson" in opp["assigned_to"]
    assert any(t["destination"] == "account_executive" for t in d["actions"]["tasks"])


def test_e_budget_is_only_what_the_customer_said(client):
    _, _, fu = _ready(client, "expansion")
    tid = fu["dynamic_variables"]["ticket_id"]
    _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="resolved",
            sales_interest="New cameras", sales_budget="around $20k")
    assert _detail(client, tid)["actions"]["opportunities"][0]["estimated_value"] == "Customer-stated budget: around $20k"


def test_f_callback_request_routes_only_to_known_teams(client):
    tid, _, fu = _ready(client)
    _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="resolved",
            callback_department="the_ceo", callback_reason="Wants to talk about the contract")
    task = _detail(client, tid)["actions"]["tasks"][0]
    assert task["destination"] == "service"  # unknown destinations fall back to the service desk


def test_unclear_hands_off_to_a_person_without_moving_the_ticket(client):
    tid, _, fu = _ready(client)
    _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="maybe?")
    d = _detail(client, tid)
    assert d["ticket"]["status"] == "follow_up_pending"
    assert d["actions"]["tasks"][0]["reason"] == "Follow-up outcome unclear"


def test_low_csat_on_a_fix_still_gets_manager_call(client):
    tid, _, fu = _ready(client)
    _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="resolved", satisfaction=2)
    d = _detail(client, tid)
    assert d["ticket"]["status"] == "closed"
    assert d["actions"]["tasks"][0]["destination"] == "service_manager"


def test_reset_is_refused_once_the_outcome_is_on_record(client):
    tid, key, fu = _ready(client)
    _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="resolved")
    assert client.post("/api/demo/reset", json={"ticket_id": tid, "demo_key": key}).status_code == 409


def test_reset_before_outcome_clears_the_pass(client):
    tid, key, fu = _ready(client)
    client.post("/api/demo/reset", json={"ticket_id": tid, "demo_key": key})
    assert _report(client, fu["dynamic_variables"]["follow_up_token"], resolution="resolved")["recorded"] is False
