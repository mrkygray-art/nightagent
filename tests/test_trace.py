"""Engineering Mode: per-call trace from our tool log plus ElevenLabs' turn timings."""
from app import evaluation
from app.service import call_ref

SAMPLE = [
    {"role": "agent", "agent_metadata": {"agent_id": evaluation.config.ELEVENLABS_AGENT_ID}, "time_in_call_secs": 0,
     "message": "Thanks for calling, this is Sam.",
     "conversation_turn_metrics": {"metrics": {"convai_llm_service_ttfb": {"elapsed_time": 0.21},
                                               "convai_tts_service_ttfb": {"elapsed_time": 0.08}}}},
    {"role": "user", "time_in_call_secs": 4, "message": "My gate will not latch tonight", "source_medium": "audio",
     "conversation_turn_metrics": {"metrics": {"convai_asr_trailing_service_latency": {"elapsed_time": 0.143}}}},
    {"role": "agent", "agent_metadata": {"agent_id": evaluation.config.ELEVENLABS_AGENT_ID}, "time_in_call_secs": 5,
     "tool_calls": [{"tool_name": "create_ticket"}],
     "conversation_turn_metrics": {"metrics": {"convai_llm_tool_request_generation_latency": {"elapsed_time": 0.4}}}},
    {"role": "agent", "agent_metadata": {"agent_id": "agent_4001m3zfgp9efne9gm350187zpfb"}, "time_in_call_secs": 6,
     "tool_results": [{"tool_name": "billing_lookup", "tool_latency_secs": 0.218, "is_error": False}]},
]


def test_turn_trace_keeps_timings_but_not_the_callers_words():
    rows = evaluation.turn_trace(SAMPLE)
    caller = next(r for r in rows if r["who"] == "Caller")
    assert caller["text"] == "Spoke (6 words)" and caller["stt_ms"] == 143
    assert "gate" not in str(rows)  # the caller's words never leave the server
    reply = rows[0]
    assert reply["who"] == "Sam" and reply["first_word_ms"] == 210 and reply["voice_ms"] == 80
    assert next(r for r in rows if r["kind"] == "tool")["decide_ms"] == 400
    result = next(r for r in rows if r["kind"] == "tool_result")
    assert result["who"] == "Jordan" and result["tool_ms"] == 218


def test_trace_endpoint_has_server_timings_right_away(client, tool):
    tool("lookup-customer", {"query": "4245550119", "conversation_id": "conv_trace_1"})
    out = client.get(f"/api/trace/{call_ref('conv_trace_1')}").json()
    assert out["tools"][0]["tool"] == "lookup_customer" and isinstance(out["tools"][0]["duration_ms"], int)
    assert out["grade"]["status"] == "unavailable" and out["turns"] == []  # no ElevenLabs key in tests


def test_trace_for_unknown_call_is_404(client):
    assert client.get("/api/trace/0123456789abcdef").status_code == 404
