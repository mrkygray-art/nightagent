"""Call check: per-call scoring from records, plus ElevenLabs' grade (faked here)."""
import pytest

from app import evaluation
from app.store import get_store


@pytest.fixture
def graded(monkeypatch):
    """Pretend ElevenLabs finished grading every call."""
    state = {"result": "success", "rationale": "No unsupported promises were made."}
    confirmed = {"result": "success", "rationale": "Name and number were read back and confirmed first."}
    monkeypatch.setattr(evaluation, "fetch_grade", lambda conv: {
        "status": "done", "summary": "Caller asked about an invoice.",
        "results": {evaluation.CRITERION: state, evaluation.CONFIRMED: confirmed}} if conv else {"status": "unavailable"})
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
    assert items["Confirmed name and number before acting"]["status"] == "pass"
    assert check["score"] == 100 and check["passed"] == check["applicable"] == 7 and check["pending"] == 1


def test_rules_correcting_the_ai_costs_points(client, tool, graded):
    check = client.get(f"/api/tickets/{_emergency(tool, suggested='urgent')}").json()["check"]
    items = _items(check)
    assert items["Identified emergency conditions"]["status"] == "fail"
    assert "rules corrected it" in items["Set the correct ticket priority"]["detail"]
    assert check["score"] == round(100 * 5 / 7)


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
    assert check["score"] == 100 and check["applicable"] == 5


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
    get_store().merge_call("conv_onphone_1", {"transcript": "Caller: Is my invoice paid?\nAgent: Your invoice is paid.\n"
                                                              "Agent: Anything else tonight?\nCaller: No."})
    detail = client.get(f"/api/calls/{call['call_id']}").json()
    rows = {r["label"]: r["value"] for r in detail["report"]["rows"]}
    assert rows["Outcome"] == "Handled on the call: no ticket or message"
    items = _items(detail["check"])
    assert items["Follow-up completed"]["status"] == "na"
    assert items["Escalation performed"]["status"] == "pass"
    assert items["Call reached an outcome"] == {**items["Call reached an outcome"], "status": "pass", "detail": "Sam closed the call"}
    assert detail["check"]["score"] == 100 and not detail["check"]["too_few"] and detail["check"]["note"] is None


def test_deepgram_call_cut_off_mid_question_is_not_100(client, tool, graded):
    """Ky's live call 2026-10-24: account found, then the call ended on Sam's question. It scored 100%."""
    tool("lookup-customer", {"query": "3105550142", "conversation_id": "dg_cutoff_1"})
    get_store().merge_call("dg_cutoff_1", {"transcript": "Agent: Just to confirm, I have you as Dave Thomas.\n"
                                           "Caller: Yes.\nAgent: Thanks.\nAgent: So when did that start?"})
    call_id = client.get("/api/calls").json()[0]["call_id"]
    detail = client.get(f"/api/calls/{call_id}").json()
    items, check = _items(detail["check"]), detail["check"]
    assert items["Call reached an outcome"]["status"] == "fail"
    assert "waiting for an answer" in items["Call reached an outcome"]["detail"]
    assert check["passed"] == 1 and check["applicable"] == 2 and check["score"] == 50
    # Deepgram calls aren't graded by ElevenLabs: say so, rather than "before this check existed"
    assert items["Avoided unsupported promises"]["detail"] == "Not graded: AI-judged checks run on ElevenLabs calls only"
    assert check["note"] == "AI-judged checks run on ElevenLabs calls only"
    rows = {r["label"]: r["value"] for r in detail["report"]["rows"]}
    assert rows["Outcome"] == "Ended before an outcome: no ticket or message"


def test_one_scored_check_is_too_few_for_a_percentage(client, tool, graded):
    tool("lookup-customer", {"query": "3105550142", "conversation_id": "dg_short_1"})  # no transcript saved
    detail = client.get(f"/api/calls/{client.get('/api/calls').json()[0]['call_id']}").json()
    check = detail["check"]
    assert _items(check)["Call reached an outcome"]["status"] == "na"
    assert check["applicable"] == 1 and check["score"] is None and check["too_few"]
    rows = {r["label"]: r["value"] for r in detail["report"]["rows"]}
    assert rows["Outcome"] == "No ticket or message"


@pytest.mark.parametrize("transcript, tools, status", [
    ("Agent: Is there anything else I can help with?\nCaller: No thanks", [], "pass"),
    ("Caller: That's all.\nAgent: Okay.\nAgent: Have a good night.", [], "pass"),
    ("Agent: What's the address?\nCaller: It's 12 Main. Bye.", [], "pass"),  # the caller said goodbye
    ("Caller: The panel is blinking.\nAgent: When did that start?", [], "fail"),
    ("Agent: How can I help?\nCaller: The back door won't lock", [], "fail"),  # no reply
    ("Agent: Let me look into that.", [], "na"),
    # The greeting isn't a close, and Deepgram sends "Just to confirm..." without its question
    ("Agent: Thanks for calling, this is Sam.\nCaller: This is James.\nAgent: Just to confirm, I have you as James Carter.", [], "fail"),
    ("Agent: Thanks for calling, this is Sam.\nCaller: Hi.\nAgent: Have a good night.\nAgent: Is that right?", [], "fail"),
    ("Agent: Thanks for calling, this is Sam. How can I help?", [], "na"),  # the caller never spoke
    ("", [], "na"),
    ("Agent: When did that start?", ["check_ticket_status"], "pass"),  # a status question answered
])
def test_call_outcome_from_the_transcript(transcript, tools, status):
    assert evaluation.call_outcome([{"tool": t} for t in tools], transcript)[0] == status


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


def test_old_single_criterion_cache_still_reads(monkeypatch):
    from app import evaluation as ev
    from app.store import get_store
    get_store().merge_call("conv_old_cache", {"eval_status": "done", "evaluation": {"result": "failure", "rationale": "Promised 9 PM."}})
    grade = ev.fetch_grade("conv_old_cache")
    assert grade["results"][ev.CRITERION]["result"] == "failure"
    check = ev.build("call", [{"tool": "lookup_customer", "outcome": "Found X"}], grade)
    items = {i["label"]: i for i in check["items"]}
    assert items["Avoided unsupported promises"]["status"] == "fail"
    assert items["Confirmed name and number before acting"]["status"] == "na"  # not graded back then
