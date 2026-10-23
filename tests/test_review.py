"""Human review rules (app/review.py), and how a flagged call lands on its Zendesk ticket."""
import hashlib
import hmac
import json
import time

import pytest

from app import config, review
from app.review import RULES, evaluate_review
from app.store import get_store
from tests.test_zendesk import zd  # noqa: F401  (the fake Zendesk fixture)

ALL_PASS = {"no_unsupported_promises": "success", "confirmed_details_first": "success", "correct_routing": "success",
            "clear_close": "success", "safety_first": "unknown", "stayed_in_scope": "unknown",
            "no_invented_facts": "success", "emergency_handled": "unknown"}


def keypad_call(**changes) -> dict:
    """A matched-account, medium-priority (urgent) alarm keypad call that went fine."""
    data = {
        "priority": "urgent", "suggested_priority": "urgent", "account_matched": True, "requester_known": True,
        "scorecard": dict(ALL_PASS), "sentiment": "calm", "intent": "service_problem", "identity_verified": True,
        "related_tickets": 0,
        "issue": "Alarm keypad shows a trouble light and keeps beeping",
        "caller_text": "Hi, this is Dave Maturo.\nMy alarm keypad has a trouble light and it keeps beeping.\nYes, that's right.",
    }
    return {**data, **changes}


def codes(result: dict) -> list[str]:
    return [r["code"] for r in result["reasons"]]


def test_keypad_call_with_a_matched_account_does_not_flag():
    result = evaluate_review(keypad_call())
    assert result == {"reviewNeeded": False, "reasons": [], "options": [], "bump_priority": False}


@pytest.mark.parametrize("changes", [{"account_matched": False}, {"requester_known": False}])
def test_no_account_match(changes):
    result = evaluate_review(keypad_call(**changes))
    assert codes(result) == ["NO_ACCOUNT_MATCH"] and result["reasons"][0]["severity"] == "High"
    assert result["options"] == ["Call back to verify identity", "Create the account and dispatch",
                                 "Send SMS asking for details"]


def test_priority_mismatch():
    result = evaluate_review(keypad_call(suggested_priority="routine"))
    assert result["reasons"] == [{"code": "PRIORITY_MISMATCH", "severity": "Medium"}]


def test_no_suggestion_recorded_is_not_a_mismatch():
    assert not evaluate_review(keypad_call(suggested_priority=None))["reviewNeeded"]


@pytest.mark.parametrize("scorecard", [
    {**ALL_PASS, "no_unsupported_promises": "failure"},  # any failure
    {**ALL_PASS, "confirmed_details_first": "unknown"},   # a check that always applies to a ticket came back unknown
])
def test_scorecard_fail_or_uncertain(scorecard):
    assert codes(evaluate_review(keypad_call(scorecard=scorecard))) == ["SCORECARD_FAIL"]


def test_unknown_on_a_check_that_does_not_apply_is_fine():
    assert not evaluate_review(keypad_call(scorecard={**ALL_PASS, "safety_first": "unknown"}))["reviewNeeded"]


def test_emergency_check_must_be_graded_once_the_ticket_is_an_emergency():
    data = keypad_call(priority="emergency", suggested_priority="emergency",
                       issue="Front door won't lock", caller_text="The front door won't lock.")
    assert not evaluate_review({**data, "scorecard": {**ALL_PASS, "emergency_handled": "success"}})["reviewNeeded"]
    assert codes(evaluate_review(data)) == ["SCORECARD_FAIL"]


@pytest.mark.parametrize("line", ["Can I talk to a real person?", "Could you have someone call me back tonight?",
                                  "I want to speak to a manager."])
def test_caller_wants_human(line):
    result = evaluate_review(keypad_call(caller_text=keypad_call()["caller_text"] + "\n" + line))
    assert result["reasons"] == [{"code": "CALLER_WANTS_HUMAN", "severity": "High"}]


def test_store_manager_giving_a_callback_number_is_not_asking_for_a_human():
    text = "I'm the store manager.\nMy callback number is •••0178, you can call me back there."
    assert not evaluate_review(keypad_call(caller_text=text))["reviewNeeded"]


@pytest.mark.parametrize("sentiment,flags", [("upset", True), ("frustrated", True), ("stressed", False), (None, False)])
def test_negative_sentiment(sentiment, flags):
    result = evaluate_review(keypad_call(sentiment=sentiment))
    assert codes(result) == (["NEGATIVE_SENTIMENT"] if flags else [])


def test_repeat_or_related():
    result = evaluate_review(keypad_call(related_tickets=2))
    assert result["reasons"] == [{"code": "REPEAT_OR_RELATED", "severity": "Medium"}]


def test_emergency_unclear_flags_and_bumps():
    result = evaluate_review(keypad_call(caller_text="The keypad is beeping and I smell something burning near it."))
    assert result["reasons"] == [{"code": "EMERGENCY_UNCLEAR", "severity": "Critical"}]
    assert result["bump_priority"] is True
    assert result["options"][0] == RULES["EMERGENCY_UNCLEAR"]["options"][0]


def test_emergency_words_on_an_emergency_ticket_are_fine():
    data = keypad_call(priority="emergency", suggested_priority="emergency", issue="Smoke from the panel",
                       scorecard={**ALL_PASS, "emergency_handled": "success"})
    assert not evaluate_review(data)["reviewNeeded"]


@pytest.mark.parametrize("line,flags", [
    ("My alarm keypad has a trouble light on, and it keeps beeping. This is not an emergency. There is no smoke.", False),
    ("There isn't any smoke and nothing is burning.", False),
    ("No smoke or fire, just the beeping.", False),
    ("It's not an emergency, but now there is smoke coming out of it.", True),  # the negation is too far back
    ("I can smell smoke.", True),
])
def test_negated_emergency_words_do_not_count(line, flags):
    """NS-4877: the caller said "There is no smoke" and the call was flagged EMERGENCY_UNCLEAR with a priority bump."""
    result = evaluate_review(keypad_call(caller_text=line))
    assert ("EMERGENCY_UNCLEAR" in codes(result)) is flags


def test_emergency_words_need_whole_words():
    assert not evaluate_review(keypad_call(caller_text="The firewall box next to the keypad is fine."))["reviewNeeded"]


@pytest.mark.parametrize("changes", [{"intent": "unclear"}, {"identity_verified": False}])
def test_low_confidence(changes):
    assert evaluate_review(keypad_call(**changes))["reasons"] == [{"code": "LOW_CONFIDENCE", "severity": "Low"}]


def test_ns_3646_unknown_caller_flags_only_for_the_missing_account():
    """The real call: an urgent keypad ticket with no account. The grader failed "Emergency handled" (Sam rightly
    didn't page on an urgent ticket) and ElevenLabs marked the call unsuccessful; neither may add a reason."""
    data = keypad_call(account_matched=False, call_successful="failure",
                       scorecard={**ALL_PASS, "safety_first": "success", "emergency_handled": "failure"})
    assert codes(evaluate_review(data)) == ["NO_ACCOUNT_MATCH"]


def test_reasons_are_ordered_by_severity_and_options_follow_the_highest():
    result = evaluate_review(keypad_call(intent="unclear", sentiment="upset", account_matched=False,
                                         caller_text="There's smoke coming out of the keypad."))
    assert codes(result) == ["EMERGENCY_UNCLEAR", "NO_ACCOUNT_MATCH", "NEGATIVE_SENTIMENT", "LOW_CONFIDENCE"]
    assert result["options"] == RULES["EMERGENCY_UNCLEAR"]["options"]


def test_note_line_and_options_text():
    result = evaluate_review(keypad_call(account_matched=False))
    assert review.note_line(result) == (
        "Needs review: NO_ACCOUNT_MATCH (no matching account or unknown caller). Suggested: Call back to verify "
        "identity; Create the account and dispatch; Send SMS asking for details.")
    assert review.options_text(result).splitlines()[0] == "1. Call back to verify identity (recommended)"
    assert review.note_line(evaluate_review(keypad_call())) is None


# ---------- call_data: where the facts come from ----------

def _ticket(tool, conv, **body):
    return tool("create-ticket", {"callback_number": "3105550178", "issue_summary": "Alarm keypad shows a trouble light",
                                  "category": "panel_trouble", "suggested_priority": "urgent",
                                  "conversation_id": conv, **body})["ticket_id"]


def test_call_data_reads_the_ticket_analysis_and_related_tickets(tool):
    first = _ticket(tool, "conv_r1", customer_id="C-1002", caller_name="James Carter")
    second = _ticket(tool, "conv_r2", customer_id="C-1002", caller_name="James Carter",
                     issue_summary="Gate keypad is dead", category="access_issue", suggested_priority="High")
    analysis = {"results": {"clear_close": {"result": "success", "rationale": "x"}},
                "data": {"caller_sentiment": "upset", "intent": "service_problem", "identity_verified": True},
                "call_successful": "success",
                "transcript": "Agent: Hi.\nCaller: Can I talk to a real person?\nAgent: I can help."}
    data = review.call_data(get_store().get_ticket(second), analysis, get_store())
    assert data["account_matched"] and data["requester_known"]
    assert data["priority"] == "routine" and data["suggested_priority"] == "routine"  # "High" isn't a priority we use
    assert data["scorecard"] == {"clear_close": "success"} and data["sentiment"] == "upset"
    assert data["caller_text"] == "Can I talk to a real person?"
    assert data["related_tickets"] == 1  # the first ticket, still open
    assert review.call_data(get_store().get_ticket(first), {}, get_store())["related_tickets"] == 1


def test_closed_ticket_older_than_a_week_is_not_related(tool):
    old = _ticket(tool, "conv_old", customer_id="C-1002", caller_name="James Carter")
    get_store().update_ticket(old, {"status": "closed", "created_at": "2026-01-01T00:00:00+00:00"})
    new = _ticket(tool, "conv_new", customer_id="C-1002", caller_name="James Carter", category="access_issue")
    assert review.call_data(get_store().get_ticket(new), {}, get_store())["related_tickets"] == 0


def test_no_account_counts_tickets_with_the_same_callback_number(tool):
    _ticket(tool, "conv_u1", caller_name="not given", callback_number="2135550100")
    new = _ticket(tool, "conv_u2", caller_name="not given", callback_number="2135550100", category="access_issue")
    data = review.call_data(get_store().get_ticket(new), {}, get_store())
    assert data["related_tickets"] == 1 and not data["account_matched"] and not data["requester_known"]


# ---------- on the Zendesk ticket ----------

def _post(client, conv, analysis):
    body = json.dumps({"type": "post_call_transcription", "data": {
        "conversation_id": conv, "agent_id": "agent_sam", "metadata": {"call_duration_secs": 60},
        "transcript": analysis.pop("transcript", []), "analysis": analysis}}).encode()
    ts = int(time.time())
    sig = f"t={ts},v0=" + hmac.new(b"test-webhook-secret", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/elevenlabs/post-call", content=body, headers={"elevenlabs-signature": sig})


def _graded(**extra):
    return {"transcript_summary": "Keypad trouble light.", "call_successful": "success",
            "evaluation_criteria_results": {k: {"result": v, "rationale": ""} for k, v in ALL_PASS.items()},
            "data_collection_results": {"caller_sentiment": {"value": "calm"}, "intent": {"value": "service_problem"},
                                        "identity_verified": {"value": True}}, **extra}


@pytest.fixture
def review_fields(monkeypatch):
    monkeypatch.setattr(config, "ZENDESK_FIELD_REVIEW_NEEDED", "501")
    monkeypatch.setattr(config, "ZENDESK_FIELD_REVIEW_REASON", "502")
    monkeypatch.setattr(config, "ZENDESK_FIELD_RECOMMENDED_OPTIONS", "503")


def _sent(zd):  # noqa: F811
    return [c["json"]["ticket"] for c in zd["calls"] if c["url"].endswith("/tickets.json")][-1]


def test_unknown_caller_ticket_is_flagged_in_zendesk(client, tool, zd, review_fields):  # noqa: F811
    _ticket(tool, "conv_flag", caller_name="not given", callback_number="2135550111")
    assert _post(client, "conv_flag", _graded()).status_code == 200
    sent = _sent(zd)
    assert sent["tags"] == ["nightagent", "needs_review", "no_account_match"]
    assert {"id": 501, "value": True} in sent["custom_fields"]
    assert {"id": 502, "value": ["no_account_match"]} in sent["custom_fields"]
    assert {"id": 503, "value": "1. Call back to verify identity (recommended)\n2. Create the account and dispatch\n"
                                "3. Send SMS asking for details"} in sent["custom_fields"]
    assert "Needs review: NO_ACCOUNT_MATCH" in sent["comment"]["body"]
    assert sent["priority"] == "high"  # urgent on the board, not bumped


def test_matched_keypad_call_is_not_flagged_in_zendesk(client, tool, zd, review_fields):  # noqa: F811
    _ticket(tool, "conv_ok", customer_id="C-1002", caller_name="James Carter")
    assert _post(client, "conv_ok", _graded()).status_code == 200
    sent = _sent(zd)
    assert sent["tags"] == ["nightagent"] and "Needs review" not in sent["comment"]["body"]
    assert not any(f["id"] in (501, 502, 503) for f in sent.get("custom_fields", []))


def test_emergency_words_bump_the_zendesk_priority_only(client, tool, zd, review_fields):  # noqa: F811
    tid = _ticket(tool, "conv_smoke", customer_id="C-1002", caller_name="James Carter",
                  issue_summary="Keypad beeping and smoke near the panel")
    _post(client, "conv_smoke", _graded())
    assert _sent(zd)["priority"] == "urgent" and "emergency_unclear" in _sent(zd)["tags"]
    assert get_store().get_ticket(tid)["priority"] == "urgent"  # the board keeps the rules' priority


def test_review_rule_crash_still_makes_the_ticket(client, tool, zd, monkeypatch):  # noqa: F811
    monkeypatch.setattr(review, "evaluate_review", lambda data: 1 / 0)
    tid = _ticket(tool, "conv_crash", customer_id="C-1002", caller_name="James Carter")
    _post(client, "conv_crash", _graded())
    assert _sent(zd)["tags"] == ["nightagent"] and get_store().get_ticket(tid)["zendesk_ticket_id"]
