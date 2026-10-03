"""The call report: tool-call log, which voice took the call, and the report rows."""
import pytest

from app import config
from tests.conftest import TOOL_HEADERS


@pytest.fixture(autouse=True)
def follow_up_agent(monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUP_AGENT_ID", "agent_followup_test")


def _rows(detail):
    return {r["label"]: r["value"] for r in detail["report"]["rows"]}


def _live_emergency(tool, conv="conv_live_123"):
    tool("lookup-customer", {"query": "4245550119", "conversation_id": conv})
    made = tool("create-ticket", {
        "customer_id": "C-1003", "caller_name": "Priya Shah", "callback_number": "424-555-0119",
        "issue_summary": "Main entrance will not unlock.", "category": "entry_blocked",
        "suggested_priority": "emergency", "conversation_id": conv,
    })
    tool("page-on-call", {"ticket_id": made["ticket_id"]})
    return made["ticket_id"]


def test_live_call_report_counts_every_tool(client, tool):
    tid = _live_emergency(tool)
    detail = client.get(f"/api/tickets/{tid}").json()
    rows = _rows(detail)
    assert [t["tool"] for t in detail["tool_calls"]] == ["lookup_customer", "create_ticket", "page_on_call_tech"]
    assert rows["Tools Sam used"].startswith("3: Looked up the account; Created the ticket; Alerted")
    assert rows["Escalated"].startswith("Yes")
    assert rows["Priority"].startswith("High priority")
    assert rows["What they needed"] == "Staff can't get in the building"
    assert rows["Ticket"] == f"{tid} created"
    assert rows["Check-in call"].startswith("Not yet")
    assert rows["Handed to"] == "Not yet" and rows["New opportunity"] == "None"


def test_lookups_from_other_calls_are_not_counted(client, tool):
    tool("lookup-customer", {"query": "Sunset", "conversation_id": "conv_someone_else"})
    tool("lookup-customer", {"query": "Sunset"})  # an old agent config without the id
    tid = _live_emergency(tool)
    assert len(client.get(f"/api/tickets/{tid}").json()["tool_calls"]) == 3


def test_voice_is_saved_only_by_the_calls_own_browser(client, tool):
    tid = _live_emergency(tool)
    bad = client.post("/api/demo/voice", json={"ticket_id": tid, "conversation_id": "conv_guess_99", "voice": "Sarah"})
    assert bad.status_code == 403
    unknown = client.post("/api/demo/voice", json={"ticket_id": tid, "conversation_id": "conv_live_123", "voice": "Bob"})
    assert unknown.status_code == 400
    ok = client.post("/api/demo/voice", json={"ticket_id": tid, "conversation_id": "conv_live_123", "voice": "sarah"})
    assert ok.status_code == 200
    # The first answer sticks
    client.post("/api/demo/voice", json={"ticket_id": tid, "conversation_id": "conv_live_123", "voice": "Eric"})
    rows = _rows(client.get(f"/api/tickets/{tid}").json())
    assert rows["Agent"] == "Sam, after-hours dispatcher (voice: Sarah)"
    assert rows["Call"] == "Voice call"


def test_text_chat_is_labeled(client, tool):
    tid = _live_emergency(tool)
    client.post("/api/demo/voice", json={"ticket_id": tid, "conversation_id": "conv_live_123", "voice": "text"})
    rows = _rows(client.get(f"/api/tickets/{tid}").json())
    assert rows["Call"] == "Text chat" and "voice:" not in rows["Agent"]


def test_example_report_is_honest_and_follow_up_fills_it_in(client):
    started = client.post("/api/demo/scenario", json={"scenario": "expansion"}).json()
    tid, key = started["ticket"]["ticket_id"], started["demo_key"]
    rows = _rows(started)
    assert rows["Call"].startswith("Example call (simulated")
    assert rows["Tools Sam used"] == "None: this example skips the call"
    for _ in range(6):
        client.post("/api/demo/advance", json={"ticket_id": tid, "demo_key": key})
    token = client.post("/api/demo/follow-up", json={"ticket_id": tid, "demo_key": key}).json()["dynamic_variables"]["follow_up_token"]
    client.post("/tools/follow-up-outcome", headers=TOOL_HEADERS, json={
        "follow_up_token": token, "conversation_id": "conv_fu_77", "resolution": "resolved", "satisfaction": 5,
        "customer_comments": "Readers work now.", "sales_interest": "Replace readers on about 14 doors",
    })
    rows = _rows(client.get(f"/api/tickets/{tid}").json())
    assert rows["Tools Sam used"] == "1: Saved the check-in result"
    assert rows["Check-in call"] == "Customer said it's fixed, rated the visit 5 out of 5"
    assert rows["Customer's words"] == "“Readers work now.”"
    assert "Account Executive" in rows["Handed to"]
    assert rows["New opportunity"] == "Replace readers on about 14 doors"


def test_old_calls_say_tools_were_not_recorded(client, tool):
    made = tool("create-ticket", {"caller_name": "A", "callback_number": "3105550100",
                                  "issue_summary": "Keypad beeping", "category": "panel_trouble"})
    from app.store import get_store
    get_store().tool_calls.clear()  # as if the call happened before tool tracking
    rows = _rows(client.get(f"/api/tickets/{made['ticket_id']}").json())
    assert rows["Tools Sam used"].startswith("Not recorded")
    assert rows["Call"] == "Live call"


def _emergency_for(tool, customer_id, phone):
    return tool("create-ticket", {
        "customer_id": customer_id, "caller_name": "Test Caller", "callback_number": phone,
        "issue_summary": "Gate will not close.", "category": "cannot_secure_site", "suggested_priority": "emergency",
    })


def test_billing_note_only_when_the_plan_lacks_after_hours(tool):
    covered = _emergency_for(tool, "C-1001", "3105550142")  # Gold: after-hours included
    assert covered["mention_billing"] is False
    page = tool("page-on-call", {"ticket_id": covered["ticket_id"]})
    assert page["mention_billing"] is False and "rate" not in page["tell_the_caller"]
    not_covered = _emergency_for(tool, "C-1002", "3105550178")  # Standard: business hours only
    assert not_covered["mention_billing"] is True
    page = tool("page-on-call", {"ticket_id": not_covered["ticket_id"]})
    assert page["mention_billing"] is True and "after-hours rate" in page["tell_the_caller"]
    unknown = _emergency_for(tool, None, "3105550100")  # no account: plan unknown, so no billing talk
    assert unknown["mention_billing"] is False
    routine = tool("create-ticket", {"customer_id": "C-1002", "caller_name": "T", "callback_number": "3105550178",
                                     "issue_summary": "Badge not working", "category": "access_issue"})
    assert routine["mention_billing"] is False


def test_lookup_asks_for_the_read_back_right_away(tool):
    out = tool("lookup-customer", {"query": "(310) 555-0178", "conversation_id": "conv_rb"})
    assert out["next_step"].startswith("In your very next reply")
    assert "I have you as James Carter at 310-555-0178" in out["next_step"]
    by_name = tool("lookup-customer", {"query": "Westside", "conversation_id": "conv_rb2"})
    assert "at 310-555-0178" in by_name["next_step"]  # falls back to the number on the account
