"""Evaluation Lab scorecard: the math, sample sizes, and what's left out."""
from app import evaluation, scorecard


def _by_label(metrics):
    return {m["label"]: m for m in metrics}


def _graded(**metrics):
    return {"eval_status": "done", "evaluation": {
        "results": {"no_unsupported_promises": {"result": "success"},
                    "confirmed_details_first": {"result": "failure"}},
        "metrics": {"cost_usd": 0.07, "answer_ms": [800, 1200], "agent_turns": 4, "interrupted": 1,
                    "tool_calls": 3, "tool_errors": 0, "transfers": 1, "transfer_errors": 0, **metrics}}}


def test_nothing_to_count_shows_no_data_not_zero():
    m = _by_label(scorecard.call_metrics([], [], {}))
    assert all(v["value"] is None and v["n"] == 0 for v in m.values())


def test_scenario_tickets_are_left_out():
    tickets = [
        {"ticket_id": "NS-1", "priority": "emergency", "paged_at": "x", "suggested_priority": "emergency"},
        {"ticket_id": "NS-2", "priority": "emergency", "paged_at": None, "suggested_priority": "urgent", "scenario": "gate"},
    ]
    m = _by_label(scorecard.call_metrics(tickets, [], {}))
    assert (m["Escalation"]["hits"], m["Escalation"]["n"]) == (1, 1)
    assert m["Priority matched the rules"]["value"] == 100


def test_call_metrics_from_tools_and_grades():
    tool_calls = [
        {"conversation_id": "c1", "tool": "lookup_customer"},
        {"conversation_id": "c1", "tool": "create_ticket", "ticket_id": "NS-1"},
        {"conversation_id": "c2", "tool": "lookup_customer"},  # hung up after the lookup
        {"conversation_id": "c3", "tool": "record_follow_up_outcome"},  # follow-up calls aren't counted
    ]
    calls = {"c1": _graded(), "c2": _graded(cost_usd=0.03, answer_ms=[2000], tool_errors=1, interrupted=0),
             "c9": {"eval_status": "pending"}}
    m = _by_label(scorecard.call_metrics([], tool_calls, calls))
    assert (m["Calls completed"]["hits"], m["Calls completed"]["n"]) == (1, 2)
    assert (m["Tool calls worked"]["hits"], m["Tool calls worked"]["n"]) == (5, 6)
    assert (m["Handoffs worked"]["hits"], m["Handoffs worked"]["n"]) == (2, 2)
    assert m["Avoided unsupported promises"]["value"] == 100 and m["Avoided unsupported promises"]["how"] == "ai"
    assert m["Confirmed details first"]["value"] == 0 and m["Confirmed details first"]["n"] == 2
    assert (m["Caller interruptions"]["hits"], m["Caller interruptions"]["n"]) == (1, 8)
    assert m["Response time"]["value"] == 1200 and m["Response time"]["n"] == 3
    assert m["Cost per call"]["value"] == 0.05 and m["Cost per call"]["total"] == 0.1


def test_test_metrics_count_only_intent_tests_for_intent():
    lab = {"status": "ok", "passed": 5, "finished": 6, "tests": [
        {"intent": True, "passed": 3, "failed": 0}, {"intent": False, "passed": 2, "failed": 1}]}
    m = _by_label(scorecard.test_metrics(lab))
    assert m["Test pass rate"]["value"] == 83
    assert (m["Intent and priority"]["hits"], m["Intent and priority"]["n"]) == (3, 3)


def test_metrics_from_a_conversation_record_keep_no_words():
    data = {"metadata": {"cost_fiat": 0.0732904, "call_duration_secs": 86}, "transcript": [
        {"role": "agent", "message": "Hi, this is Sam.",
         "conversation_turn_metrics": {"metrics": {"convai_ttf_audio_since_silence": {"elapsed_time": 0.09}}}},
        {"role": "user", "message": "My gate is stuck"},
        {"role": "agent", "message": "Sorry to hear", "interrupted": True,
         "conversation_turn_metrics": {"metrics": {"convai_ttf_audio_since_silence": {"elapsed_time": 0.83}}}},
        {"role": "agent", "tool_results": [{"tool_name": "lookup_customer", "is_error": False},
                                           {"tool_name": "transfer_to_agent", "is_error": True}]},
    ]}
    m = evaluation.call_metrics(data)
    assert m == {"cost_usd": 0.07329, "duration_s": 86, "answer_ms": [830], "agent_turns": 2, "interrupted": 1,
                 "tool_calls": 1, "tool_errors": 0, "transfers": 1, "transfer_errors": 1}


def test_api_lab_includes_the_scorecard(client):
    scorecard._cache.update(at=0.0, data=None)
    body = client.get("/api/lab").json()
    assert "scorecard" in body and {m["label"] for m in body["scorecard"]["calls"]} >= {"Escalation", "Cost per call"}


def test_backfill_grades_unopened_calls_first_and_stuck_ones_last(monkeypatch):
    seen = []

    def fake_grade(cid, want_metrics=False):
        seen.append(cid)
        return {"status": "done", "results": {}, "metrics": {"cost_usd": 0.01}}

    monkeypatch.setattr(scorecard.config, "ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setattr(scorecard.evaluation, "fetch_grade", fake_grade)
    monkeypatch.setattr(scorecard, "BACKFILL_PER_REQUEST", 3)
    calls = {"stuck": {"eval_status": "pending"},
             "old": {"eval_status": "done", "evaluation": {"results": {}}},
             "ready": _graded()}
    ids = ["stuck", "old", "ready", "never1", "never2"]
    scorecard._backfill(ids, calls)
    assert seen == ["never1", "never2", "old"]
    assert calls["never1"]["eval_status"] == "done" and calls["never1"]["evaluation"]["metrics"]["cost_usd"] == 0.01
