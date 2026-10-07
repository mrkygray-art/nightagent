"""Post-call analysis (webhook and data collection), the AI-judge agreement check, and the safety watchdog."""
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone

from app import analysis_spec, judge, metrics, watchdog
from app.service import call_ref
from app.store import get_store


def _post(client, data):
    body = json.dumps({"type": "post_call_transcription", "data": data}).encode()
    ts = int(time.time())
    sig = f"t={ts},v0=" + hmac.new(b"test-webhook-secret", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return client.post("/webhooks/elevenlabs/post-call", content=body, headers={"elevenlabs-signature": sig})


CALL = {
    "conversation_id": "conv_q_1", "agent_id": "agent_sam", "status": "done",
    "metadata": {"call_duration_secs": 95, "cost_fiat": 0.05},
    "transcript": [{"role": "agent", "message": "Hi, this is Sam."},
                   {"role": "user", "message": "It's Maria, 310-555-0142, back door won't lock."}],
    "analysis": {
        "transcript_summary": "Back door won't lock; ticket made and technician paged.",
        "call_successful": "success",
        "evaluation_criteria_results": {"safety_first": {"result": "unknown", "rationale": "No danger"},
                                        "emergency_handled": {"result": "success", "rationale": "Paged"}},
        "data_collection_results": {"intent": {"value": "service_problem"}, "identity_verified": {"value": True},
                                    "identity_method": {"value": "account_lookup_and_readback"},
                                    "caller_sentiment": {"value": "stressed"}, "resolved_on_call": {"value": False}},
    },
}


def test_webhook_stores_the_whole_analysis_with_numbers_redacted(client):
    assert _post(client, CALL).json()["status"] == "ok"
    row = get_store().calls["conv_q_1"]
    assert row["duration_secs"] == 95 and row["agent_id"] == "agent_sam" and row["eval_status"] == "done"
    assert row["evaluation"]["results"]["emergency_handled"]["result"] == "success"
    assert row["evaluation"]["data"]["intent"] == "service_problem"
    assert "310-555-0142" not in row["transcript"] and "0142" in row["transcript"]


def test_data_collection_reaches_impact_and_the_ticket(client, tool):
    tool("lookup-customer", {"query": "3105550142", "conversation_id": "conv_q_1"})
    t = tool("create-ticket", {"customer_id": "C-1001", "caller_name": "Maria", "callback_number": "3105550142",
                               "issue_summary": "Back door will not lock", "category": "door_wont_lock",
                               "conversation_id": "conv_q_1"})
    tool("page-on-call", {"ticket_id": t["ticket_id"]})
    _post(client, CALL)
    live = client.get("/api/impact").json()["views"]["live"]
    assert live["classified"] == 1 and live["top_reasons"][0]["intent"] == "service_problem"
    assert client.get("/api/impact").json()["live_only"]["aht_seconds"] == 95
    v = client.get(f"/api/tickets/{t['ticket_id']}").json()["view"]
    assert v["identity"]["verified"] is True and v["sentiment"] == "Stressed"
    assert v["intent"]["detected"] == metrics.INTENT_LABELS["service_problem"]
    assert v["handoff"]["count"] == 5  # summary, transcript, account, actions, identity
    assert v["transcript"] is None  # still never shown for a live call


def test_agent_payload_matches_what_the_code_reads():
    payload = analysis_spec.agent_payload()
    ids = [c["id"] for c in payload["evaluation"]["criteria"]]
    assert ids == list(analysis_spec.CRITERIA_IDS) and len(ids) == len(set(ids)) == 8
    assert all(len(c["conversation_goal_prompt"]) <= 2000 and "Unknown" in c["conversation_goal_prompt"]
               for c in payload["evaluation"]["criteria"])
    assert set(payload["data_collection"]) == {"intent", "identity_verified", "identity_method",
                                               "caller_sentiment", "resolved_on_call"}
    assert set(analysis_spec.DATA_FIELDS["intent"]["enum"]) == set(metrics.INTENT_LABELS)


def test_judge_agreement_and_kappa():
    calls = {f"conv_j{i}": {"evaluation": {"results": {"clear_close": {"result": r}}}}
             for i, r in enumerate(["success", "success", "failure", "failure", "unknown"])}
    labels = [{"call_ref": call_ref(f"conv_j{i}"), "criterion": "clear_close", "human": h}
              for i, h in enumerate(["success", "failure", "failure", "failure", "success"])]
    a = judge.agreement(calls, labels)
    assert (a["n"], a["agree"], a["rate"], a["left_out"]) == (4, 3, 75, 1)
    assert a["kappa"] == 0.5 and a["disagreements"][0]["person"] == "failure"
    assert judge.agreement(calls, [])["status"] == "none"


def test_watchdog_flags_an_emergency_that_was_never_alerted(client, tool):
    paged = tool("create-ticket", {"customer_id": "C-1001", "caller_name": "M", "callback_number": "3105550142",
                                   "issue_summary": "Door", "category": "door_wont_lock", "conversation_id": "conv_w1"})
    tool("page-on-call", {"ticket_id": paged["ticket_id"]})
    missed = tool("create-ticket", {"customer_id": "C-1003", "caller_name": "P", "callback_number": "4245550119",
                                    "issue_summary": "Entrance", "category": "entry_blocked", "conversation_id": "conv_w2"})
    client.post("/api/demo/scenario", json={"scenario": "emergency_resolved"})  # synthetic: never counted
    w = watchdog.watchdog()
    assert (w["emergencies"], w["paged"], w["waiting"], w["missed"]) == (2, 1, 1, [])
    later = datetime.now(timezone.utc) + timedelta(minutes=watchdog.PAGE_DEADLINE_MINUTES + 1)
    w = watchdog.watchdog(now=later)
    assert [m["ticket_id"] for m in w["missed"]] == [missed["ticket_id"]]
    assert w["missed"][0]["reason"] == "Sam never asked for an alert"
    assert w["ticket_to_page"]["n"] == 1
    assert client.get("/api/lab").json()["watchdog"]["emergencies"] == 2


def test_redaction_catches_numbers_read_out_as_words():
    from app.evaluation import redact
    said = ("Agent: Just to confirm, I have you as Maria at three one oh, five five five, oh one four two. "
            "Caller: Yes. My other line is 424-555-0119, or (310) 555 0178, double five times. "
            "Agent: Ticket NS-1234 for one door, opened 2026-10-07. Email me at a.b@x.com")
    out = redact(said)
    for full in ("three one oh, five five five", "424-555-0119", "555 0178", "a.b@x.com"):
        assert full not in out
    assert out.count("•••") == 3 and "•••0142" in out and "•••0119" in out and "•••0178" in out
    # Short numbers stay: ticket numbers, counts, dates
    assert "NS-1234" in out and "one door" in out and "2026-10-07" in out
