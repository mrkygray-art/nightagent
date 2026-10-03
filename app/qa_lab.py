"""Agent QA Lab: regression tests built from real problems found in live calls, run in
ElevenLabs Agent Testing against the live agents. This module reads the latest results back
from ElevenLabs and boils them down to what the public /lab page shows.

Only reply text, tool names, and tool parameters leave this module. ElevenLabs also returns
each tool call's request headers (which carry our tool secret); those are never passed on.
"""
from __future__ import annotations

import logging
import re
import time

import requests

from app import config

log = logging.getLogger("nightshift")

API = "https://api.elevenlabs.io/v1/convai"
CACHE_SECONDS = 60

SAM = config.ELEVENLABS_AGENT_ID
JORDAN = "agent_4001m3zfgp9efne9gm350187zpfb"
RILEY = "agent_3001m3zg26pted8trz8p4pxt4qfc"
AGENTS = {SAM: "Sam (front desk)", JORDAN: "Jordan (billing assistant)", RILEY: "Riley (sales assistant)"}

# Each test, and the real problem it was written after. Order is the order on the page.
TESTS = {
    "test_2801m3ztgsfxemxsvmqbhm8n66zv": {
        "name": "QA-01 Reads back name and number right after lookup",
        "agent": SAM, "kind": "Reply check",
        "why": "In a live call Sam found the account and went straight to the problem without reading the "
               "caller's name and number back first.",
        "checks": "Right after the account lookup, Sam reads back the name and number and asks if they're right.",
    },
    "test_4701m3ztgtace1st09hxq2d5s4w7": {
        "name": "QA-02 No ticket before the caller confirms",
        "agent": SAM, "kind": "Tool check",
        "why": "Same call: acting before the caller confirms their details can send a technician to the wrong person.",
        "checks": "Sam does not call create_ticket until the caller has confirmed.",
    },
    "test_6501m3ztgvfmesk80c6g9r0qh2mj": {
        "name": "QA-03 Gate stuck open is an emergency",
        "agent": SAM, "kind": "Tool check",
        "why": "A gate stuck open was suggested at medium priority. A site that can't be secured is an emergency.",
        "checks": "Sam calls create_ticket with category cannot_secure_site and suggested priority emergency.",
    },
    "test_8301m3ztgwmxfe9t4xn5wj284am3": {
        "name": "QA-04 Says the after-hours billing line when the plan doesn't cover it",
        "agent": SAM, "kind": "Reply check",
        "why": "Sam once left out that an after-hours visit is billed extra for a business-hours-only plan.",
        "checks": "After paging the technician, Sam gives the callback window, the ticket number, and the billing sentence.",
    },
    "test_2501m3ztgxz1ewcv3xsvn7ysrzee": {
        "name": "QA-05 No billing line for a customer whose plan covers after hours",
        "agent": SAM, "kind": "Reply check",
        "why": "Sam once told a customer with 24/7 coverage that they'd be billed extra.",
        "checks": "For a covered customer, Sam gives the callback window and ticket number with no billing note.",
    },
    "test_7901m3ztgyxrfsfv8bp4p56s7tc4": {
        "name": "QA-06 Off-topic request (hamburger and soda)",
        "agent": SAM, "kind": "Reply check",
        "why": "Testing the unexpected: a caller orders a cheeseburger and a soda.",
        "checks": "Sam kindly says it can only help with security, billing, or reaching someone, and takes no order.",
    },
    "test_0001m3ztgzqse6nvd277ynbt40f7": {
        "name": "QA-07 Supervisor request with a broken gate: ticket first",
        "agent": SAM, "kind": "Tool check",
        "why": "A caller asked for a supervisor about a gate that still wouldn't close. The complaint must not "
               "hide the repair.",
        "checks": "Sam opens an emergency repair ticket first (the message for the service manager comes after).",
    },
    "test_1701m3zth0dre1ssztwxsxjvdwjp": {
        "name": "QA-08 Jordan speaks as Jordan, in the first person",
        "agent": JORDAN, "kind": "Reply check",
        "why": "After a handoff, Jordan talked about itself in the third person (\"Jordan will look into it\").",
        "checks": "Jordan speaks as Jordan, in the first person, and promises no refund or credit.",
    },
    "test_9301m3zvs7m2erxv8vmhz6c9j862": {
        "name": "QA-09 Same problem reported twice: no second alert",
        "agent": SAM, "kind": "Tool check",
        "why": "Failure injection: a second call about the same gate opened a duplicate ticket and told Sam to alert "
               "the technician again. The server now joins it to the open ticket and says the technician has it.",
        "checks": "When the server says the problem is already on an open ticket, Sam does not alert the technician again.",
    },
    "test_0901m3zvs8p2fjz9ffx1rtnv7htr": {
        "name": "QA-10 Same problem reported twice: points to the open ticket",
        "agent": SAM, "kind": "Reply check",
        "why": "Same failure: the second caller should hear that help is already on the way, not get a new ticket.",
        "checks": "Sam gives the existing ticket number, says the technician already has it, and mentions no new ticket or charge.",
    },
    "test_6601m3zwjpwcfakvag35zsj5s993": {
        "name": "QA-11 Riley never quotes a price",
        "agent": RILEY, "kind": "Reply check",
        "why": "Testing the unexpected: a caller pushes Riley for a ballpark price. Only the account executive can quote.",
        "checks": "Riley gives no price, range, or estimate, says Sarah Johnson will handle the quote, and keeps gathering details.",
    },
    "test_5001m3zwjqnzea5b9kv5603yxkwq": {
        "name": "QA-12 Riley records the lead with what the caller said",
        "agent": RILEY, "kind": "Tool check",
        "why": "Riley once filled in \"not specified\" for details the caller never gave. The server now drops those; this "
               "checks the details the caller did give arrive intact.",
        "checks": "Riley calls record_sales_interest with four cameras, next month, weekday mornings, and the confirmed number.",
    },
}

_cache: dict = {"at": 0.0, "data": None}


def _get(path: str, params: dict | None = None) -> dict:
    res = requests.get(f"{API}{path}", params=params or {}, timeout=8,
                       headers={"xi-api-key": config.ELEVENLABS_API_KEY})
    res.raise_for_status()
    return res.json()


def _clean(text: str) -> str:
    text = re.sub(r"\[[a-z][a-z ]{1,24}\]\s*", "", text or "")  # voice-style tags like [calm]
    return re.sub(r"\s+", " ", text).strip()[:320]


def _what_it_did(run: dict) -> str:
    """The agent's reply in a test run: its words, or the tool it called with its parameters."""
    parts = []
    for turn in run.get("agent_responses") or []:
        if turn.get("message"):
            parts.append(_clean(turn["message"]))
        for call in turn.get("tool_calls") or []:
            parts.append(f"Called {call.get('tool_name')} {_clean(call.get('params_as_json') or '')}")
    return " · ".join(p for p in parts if p)[:420]


def summarize(invocation: dict) -> list[dict]:
    """One row per test in a suite run: passes out of finished runs, plus one example."""
    rows: dict[str, dict] = {}
    for run in invocation.get("test_runs") or []:
        tid = run.get("test_id")
        if tid not in TESTS:
            continue
        row = rows.setdefault(tid, {"test_id": tid, "name": run.get("test_name", tid), "passed": 0, "failed": 0,
                                    "pending": 0, "example": None, "failure": None})
        status = run.get("status")
        summary = ((run.get("condition_result") or {}).get("rationale") or {}).get("summary") or ""
        example = {"reply": _what_it_did(run), "judge": _clean(summary)}
        if status == "passed":
            row["passed"] += 1
            row["example"] = row["example"] or example
        elif status == "failed":
            row["failed"] += 1
            row["failure"] = row["failure"] or example
        else:
            row["pending"] += 1
    return list(rows.values())


def _recent(agent_id: str) -> list[dict]:
    """This agent's recent suite runs that include lab tests, newest first."""
    listing = _get("/test-invocations", {"agent_id": agent_id, "page_size": 10})
    found = []
    for item in listing.get("results") or []:
        full = _get(f"/test-invocations/{item.get('id') or item.get('test_invocation_id')}")
        if any(r.get("test_id") in TESTS for r in full.get("test_runs") or []):
            found.append(full)
    return sorted(found, key=lambda inv: inv.get("created_at") or 0, reverse=True)


def lab_results() -> dict:
    if _cache["data"] and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    if not config.ELEVENLABS_API_KEY:
        return {"status": "unavailable", "reason": "Results can't be read on this server.", "tests": []}
    try:
        # Each test shows its own most recent run, so a quick one-test check doesn't hide the rest
        by_test: dict[str, dict] = {}
        for agent_id in AGENTS:
            for inv in _recent(agent_id):
                for row in summarize(inv):
                    if row["test_id"] not in by_test:
                        by_test[row["test_id"]] = {**row, "ran_at": inv.get("created_at")}
    except Exception:  # noqa: BLE001 - the page should still load
        log.exception("Could not read QA Lab results from ElevenLabs")
        return {"status": "unavailable", "reason": "Couldn't reach ElevenLabs just now.", "tests": []}
    tests = []
    for tid, meta in TESTS.items():
        row = by_test.get(tid) or {"test_id": tid, "passed": 0, "failed": 0, "pending": 0,
                                   "example": None, "failure": None}
        tests.append({**row, "name": meta["name"], "agent": AGENTS[meta["agent"]], "kind": meta["kind"], "why": meta["why"],
                      "checks": meta["checks"]})
    passed = sum(t["passed"] for t in tests)
    finished = passed + sum(t["failed"] for t in tests)
    data = {"status": "ok", "last_run": max((t.get("ran_at") or 0 for t in tests), default=0) or None, "tests": tests, "passed": passed, "finished": finished,
            "pass_rate": round(100 * passed / finished) if finished else None,
            "pending": sum(t["pending"] for t in tests)}
    _cache.update(at=time.time(), data=data)
    return data
