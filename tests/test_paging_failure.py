"""A failed alert never ends the call: the ticket stays, the failure is recorded, and a retry works."""
from app import routes_tools
from app.store import get_store

EMERGENCY = {"customer_id": "C-1003", "caller_name": "Priya Shah", "callback_number": "4245550119",
             "issue_summary": "Main entrance won't unlock", "category": "entry_blocked",
             "suggested_priority": "emergency", "conversation_id": "conv_down_1"}


def test_paging_error_is_answered_recorded_and_retryable(client, tool, monkeypatch):
    tid = tool("create-ticket", EMERGENCY)["ticket_id"]

    def down(body):
        raise ConnectionError("Paging service unavailable")

    monkeypatch.setattr(routes_tools, "page_on_call", down)
    failed = tool("page-on-call", {"ticket_id": tid})
    assert failed["paged"] is False and failed["alert_failed"] is True
    assert "Do not promise a callback time" in failed["next_step"]
    assert not get_store().get_ticket(tid).get("paged_at")
    events = [e["event_type"] for e in client.get(f"/api/tickets/{tid}").json()["events"]]
    assert "page_failed" in events

    monkeypatch.undo()
    back = tool("page-on-call", {"ticket_id": tid})
    assert back["paged"] is True and get_store().get_ticket(tid).get("paged_at")


def test_paging_down_scenario_runs_in_a_sandbox(client):
    result = client.post("/api/lab/inject/paging-down").json()
    assert result["passed"] and len(result["checks"]) == 6
    assert get_store().tickets == {}


def test_injected_paging_failure_only_works_in_a_sandbox():
    from app.notify import page_on_call, paging_down
    with paging_down():
        assert page_on_call("outside a sandbox")["simulated"] is True  # no failure, no real text
