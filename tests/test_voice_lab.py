"""Voice tests: the /lab summary, and keeping test calls out of the real-call numbers."""
from app import scorecard, voice_lab
from app.service import log_tool_call

RUN = {
    "run_at": 1791070000,
    "voices": ["Jessica (ElevenLabs premade, American female)"],
    "results": [
        {"test": "numbers", "condition": "clean", "caller": "maria", "conversation_id": "conv_test1",
         "heard": "Maria Lopez 310-555-0142", "number_heard": True, "name_heard": True, "read_back_right": True,
         "response_ms": 900, "started_before_caller_finished": False, "turn_split": False},
        {"test": "numbers", "condition": "cafe-0", "caller": "james", "conversation_id": "conv_test2",
         "heard": "James Carter 310 555 01", "number_heard": False, "name_heard": True, "read_back_right": False,
         "response_ms": 1500, "started_before_caller_finished": True, "turn_split": True},
        {"test": "interruption", "conversation_id": "conv_test3", "passed": True, "stop_ms": 350,
         "reply": "[concerned] Okay, so the back door won't lock.", "response_ms": 800},
        {"test": "silence", "conversation_id": "conv_test4", "passed": True, "check_in_ms": 19000,
         "first_reply_ms": 4800, "spoke_during_silence": [{"after_ms": 4800, "text": "What's happening?"},
                                                          {"after_ms": 19000, "text": "Are you still there?"}]},
    ],
    "other_test_conversations": ["conv_trial"],
}


def _use(monkeypatch, data):
    monkeypatch.setattr(voice_lab, "_load", lambda: data)


def test_summary_counts_and_hides_conversation_ids(monkeypatch):
    s = voice_lab.summary(RUN)
    assert "conv_" not in str(s)
    clean, loud = s["numbers"]
    assert (clean["condition"], clean["number_heard"], clean["calls"]) == ("Quiet room", 1, 1)
    assert (loud["condition"], loud["number_heard"], loud["started_early"], loud["turn_split"]) == ("Loud café (0 dB)", 0, 1, 1)
    assert loud["misses"] == [{"heard": "James Carter 310 555 01", "caller": "james", "reply": ""}]
    assert clean["misses"] == []
    assert s["interruption"]["passed"] == 1 and s["interruption"]["timing"]["typical_ms"] == 350
    assert s["interruption"]["example"]["reply"] == "Okay, so the back door won't lock."  # voice tags stripped
    assert s["silence"]["timing"]["typical_ms"] == 19000 and s["silence"]["first_reply"]["typical_ms"] == 4800
    assert s["response_time"]["all"]["n"] == 3 and s["response_time"]["quiet"]["typical_ms"] == 900


def test_no_saved_run():
    assert voice_lab.summary({}) == {"status": "none"}


def test_test_calls_stay_out_of_real_call_numbers(client, monkeypatch):
    _use(monkeypatch, RUN)
    log_tool_call("lookup_customer", "Found Sunset Dental Group", conversation_id="conv_test1")
    log_tool_call("lookup_customer", "Found Sunset Dental Group", conversation_id="conv_trial")
    log_tool_call("lookup_customer", "Found Westside Self Storage", conversation_id="conv_real")

    calls = client.get("/api/calls").json()
    assert [c["customer"] for c in calls] == ["Westside Self Storage"]
    assert client.get("/api/impact").json()["views"]["live"]["contacts"] == 1

    scorecard._cache.update(at=0.0, data=None)
    m = {x["label"]: x for x in scorecard.scorecard({"status": "unavailable"})["calls"]}
    assert m["Calls completed"]["n"] == 1
    scorecard._cache.update(at=0.0, data=None)


def test_voice_metrics_join_the_test_scorecard():
    m = {x["label"]: x for x in scorecard.voice_metrics(voice_lab.summary(RUN))}
    assert (m["Phone number heard exactly (voice tests)"]["hits"], m["Phone number heard exactly (voice tests)"]["n"]) == (1, 2)
    assert m["Caller wait (voice tests)"]["n"] == 3
    assert scorecard.voice_metrics({"status": "none"}) == []
