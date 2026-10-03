"""Agent QA Lab: results read from ElevenLabs Agent Testing, summarized for the public /lab page."""
from app import config, qa_lab

GATE = "test_6501m3ztgvfmesk80c6g9r0qh2mj"
OFF_TOPIC = "test_7901m3ztgyxrfsfv8bp4p56s7tc4"


def _run(test_id, status, message=None, params=None, summary="ok"):
    turns = []
    if message:
        turns.append({"role": "agent", "message": message})
    if params:
        turns.append({"role": "agent", "tool_calls": [{
            "tool_name": "create_ticket", "params_as_json": params,
            "tool_details": {"headers": {"x-tool-secret": "SECRET-SHOULD-NOT-LEAK"}, "url": "https://example.test"}}]})
    return {"test_id": test_id, "test_name": f"QA {test_id}", "status": status, "agent_responses": turns,
            "condition_result": {"rationale": {"summary": summary}}}


INVOCATION = {"created_at": 1790995724, "repeat_count": 3, "version_id": "v1", "test_runs": [
    _run(GATE, "passed", params='{"category": "cannot_secure_site", "suggested_priority": "emergency"}'),
    _run(GATE, "passed", params='{"category": "cannot_secure_site", "suggested_priority": "emergency"}'),
    _run(GATE, "failed", params='{"category": "cannot_secure_site", "suggested_priority": "urgent"}',
         summary="Parameter evaluation failed"),
    _run(OFF_TOPIC, "passed", message="[calm] Sorry, I can't take food orders.   Can I help with your security system?"),
    _run(OFF_TOPIC, "pending"),
    _run("test_someone_elses", "passed", message="not ours"),
]}


def test_summary_counts_passes_and_keeps_one_example_of_each():
    rows = {r["test_id"]: r for r in qa_lab.summarize(INVOCATION)}
    assert set(rows) == {GATE, OFF_TOPIC}  # tests that aren't part of the lab are ignored
    gate = rows[GATE]
    assert (gate["passed"], gate["failed"], gate["pending"]) == (2, 1, 0)
    assert "emergency" in gate["example"]["reply"] and "urgent" in gate["failure"]["reply"]
    assert gate["failure"]["judge"] == "Parameter evaluation failed"
    off = rows[OFF_TOPIC]
    assert off["example"]["reply"] == "Sorry, I can't take food orders. Can I help with your security system?"
    assert off["pending"] == 1


def test_tool_secret_never_leaves_the_server():
    assert "SECRET-SHOULD-NOT-LEAK" not in str(qa_lab.summarize(INVOCATION))


def test_lab_endpoint_reads_the_latest_run_for_each_agent(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "test-key")
    qa_lab._cache.update(at=0.0, data=None)
    calls = []

    def fake_get(path, params=None):
        calls.append(path)
        if path == "/test-invocations":
            return {"results": [{"id": "suite_1"}]} if params["agent_id"] == qa_lab.SAM else {"results": []}
        return INVOCATION

    monkeypatch.setattr(qa_lab, "_get", fake_get)
    data = client.get("/api/lab").json()
    assert data["status"] == "ok" and data["passed"] == 3 and data["finished"] == 4 and data["pass_rate"] == 75
    assert len(data["tests"]) == len(qa_lab.TESTS)  # tests with no run yet still show, as "not run yet"
    assert next(t for t in data["tests"] if t["test_id"] == GATE)["why"].startswith("A gate stuck open")
    assert "SECRET-SHOULD-NOT-LEAK" not in str(data)
    client.get("/api/lab")
    assert calls.count("/test-invocations") == len(qa_lab.AGENTS)  # second request served from the cache
    qa_lab._cache.update(at=0.0, data=None)


def test_lab_without_a_key_says_so(client, monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    qa_lab._cache.update(at=0.0, data=None)
    assert client.get("/api/lab").json()["status"] == "unavailable"
    assert "Evaluation Lab" in client.get("/lab").text
