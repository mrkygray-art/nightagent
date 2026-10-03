"""Call check: per-call scoring from records, plus ElevenLabs' grade (faked here)."""
import pytest

from app import evaluation


@pytest.fixture
def graded(monkeypatch):
    """Pretend ElevenLabs finished grading every call."""
    state = {"result": "success", "rationale": "No unsupported promises were made."}
    monkeypatch.setattr(evaluation, "fetch_grade", lambda conv: {"status": "done", **state, "summary": "Caller asked about an invoice."} if conv else {"status": "unavailable"})
    return state


def _items(check):
    return {i["label"]: i for i in check["items"]}


def _emergency(tool, conv="conv_check_1", suggested="emergency"):
    tool("lookup-customer", {"query": "4245550119", "conversation_id": conv})
    made = tool("create-ticket", {"customer_id": "C-1003", "caller_name": "Priya Shah", "callback_number": "4245550119",
                                  "issue_summary": "Main entrance won't unlock", "category": "entry_blocked",
                                  "suggested_priority": suggested, "conversation_id": conv})
    tool("page-on-call", {"ticket_id": made["ticket_id"]})
    return made["ticket_id"]


def test_emergency_call_scores_every_applicable_check(client, tool, graded):
    check = client.get(f"/api/tickets/{_emergency(tool)}").json()["check"]
    items = _items(check)
    assert items["Identified the customer"]["status"] == "pass"
    assert items["Determined the location"]["status"] == "pass"
    assert items["Identified emergency conditions"]["status"] == "pass"
    assert items["Set the correct ticket priority"]["status"] == "pass"
    assert items["Avoided unsupported promises"] == {**items["Avoided unsupported promises"], "status": "pass", "how": "ai"}
    assert items["Escalation needed"]["status"] == "info"
    assert items["Escalation performed"]["status"] == "pass"
    assert items["Follow-up completed"]["status"] == "pending"  # check-in call comes later
    assert check["score"] == 100 and check["passed"] == check["applicable"] == 6 and check["pending"] == 1


def test_rules_correcting_the_ai_costs_points(client, tool, graded):
    check = client.get(f"/api/tickets/{_emergency(tool, suggested='urgent')}").json()["check"]
    items = _items(check)
    assert items["Identified emergency conditions"]["status"] == "fail"
    assert "rules corrected it" in items["Set the correct ticket priority"]["detail"]
    assert check["score"] == round(100 * 4 / 6)


def test_a_promise_flagged_by_elevenlabs_is_a_failure(client, tool, graded):
    graded.update(result="failure", rationale="Sam promised a technician by 9 PM.")
    item = _items(client.get(f"/api/tickets/{_emergency(tool)}").json()["check"])["Avoided unsupported promises"]
    assert item["status"] == "fail" and "9 PM" in item["detail"]


def test_billing_handoff_marks_repair_checks_not_applicable(client, tool, graded):
    tool("lookup-customer", {"query": "4245550119", "conversation_id": "conv_bill_9"})
    tool("billing-lookup", {"customer_id": "C-1003", "conversation_id": "conv_bill_9"})
    review = tool("billing-review", {"customer_id": "C-1003", "invoice_id": "INV-1003-0926", "reason": "Charged twice",
                                     "caller_name": "Priya Shah", "callback_number": "4245550119", "conversation_id": "conv_bill_9"})
    check = client.get(f"/api/messages/{review['review_id']}").json()["check"]
    items = _items(check)
    for label in ("Determined the location", "Identified emergency conditions", "Set the correct ticket priority"):
        assert items[label]["status"] == "na"
    assert items["Escalation performed"]["detail"] == "Handed off to Jordan, the billing assistant"
    assert items["Follow-up completed"]["status"] == "pass"
    assert check["score"] == 100 and check["applicable"] == 4


def test_billing_message_without_handoff_fails_escalation(client, tool, graded):
    tool("lookup-customer", {"query": "4245550119", "conversation_id": "conv_msg_9"})
    mid = tool("take-message", {"department": "billing", "reason": "Invoice question", "caller_name": "Priya Shah",
                                "callback_number": "4245550119", "conversation_id": "conv_msg_9"})["message_id"]
    item = _items(client.get(f"/api/messages/{mid}").json()["check"])["Escalation performed"]
    assert item["status"] == "fail" and "instead of handing off" in item["detail"]


def test_call_handled_on_the_phone_shows_on_the_board(client, tool, graded):
    tool("lookup-customer", {"query": "3105550142", "conversation_id": "conv_onphone_1"})
    tool("billing-lookup", {"customer_id": "C-1001", "conversation_id": "conv_onphone_1"})
    _emergency(tool, conv="conv_has_ticket")  # calls with a ticket stay off this list
    board = client.get("/api/calls").json()
    assert len(board) == 1
    call = board[0]
    assert call["customer"] == "Sunset Dental Group" and call["call_id"].startswith("CALL-")
    assert call["agents"] == "Sam (front desk) → Jordan (billing assistant)"
    detail = client.get(f"/api/calls/{call['call_id']}").json()
    rows = {r["label"]: r["value"] for r in detail["report"]["rows"]}
    assert rows["Outcome"].startswith("Handled on the call")
    items = _items(detail["check"])
    assert items["Follow-up completed"]["status"] == "na"
    assert items["Escalation performed"]["status"] == "pass"
    assert detail["check"]["score"] == 100


def test_voice_for_a_phone_only_call(client, tool, graded):
    tool("lookup-customer", {"query": "3105550142", "conversation_id": "conv_onphone_2"})
    call_id = client.get("/api/calls").json()[0]["call_id"]
    assert client.post("/api/demo/voice", json={"ticket_id": call_id, "conversation_id": "conv_wrong_99", "voice": "Lauren"}).status_code == 403
    assert client.post("/api/demo/voice", json={"ticket_id": call_id, "conversation_id": "conv_onphone_2", "voice": "Lauren"}).status_code == 200
    rows = {r["label"]: r["value"] for r in client.get(f"/api/calls/{call_id}").json()["report"]["rows"]}
    assert rows["Agent"].endswith("(voice: Lauren)")


def test_examples_have_no_call_check(client):
    started = client.post("/api/demo/scenario", json={"scenario": "expansion"}).json()
    assert started["check"] is None


def test_without_a_key_the_ai_check_is_not_available(client, tool):
    item = _items(client.get(f"/api/tickets/{_emergency(tool)}").json()["check"])["Avoided unsupported promises"]
    assert item["status"] == "na"
