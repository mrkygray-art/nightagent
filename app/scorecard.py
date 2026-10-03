"""Evaluation Lab scorecard: how well the agents do, from records we already keep.

Two groups that are never blended: "in tests" (ElevenLabs Agent Testing runs) and "on real calls"
(tickets, tool logs, and each call's ElevenLabs record). Every metric carries its sample size, and a
metric with nothing to count says so instead of showing 0%. Scenario tickets are made-up demo data,
so they're left out; failure-injection runs use a sandbox store and never reach these tables.
"""
from __future__ import annotations

import logging
import statistics
import time

from app import config, evaluation, qa_lab, voice_lab
from app.store import get_store

log = logging.getLogger("nightshift")

CACHE_SECONDS = 60
BACKFILL_PER_REQUEST = 5  # calls not yet graded, or graded before metrics were saved: a few per page view
OUTCOME_TOOLS = {"create_ticket", "take_message", "request_billing_review", "record_sales_interest"}
SPECIALIST_TOOLS = evaluation.SPECIALIST_TOOLS

_cache: dict = {"at": 0.0, "data": None}


def metric(label: str, hits: int, n: int, definition: str, *, how: str = "rules") -> dict:
    """A share: value is a percentage, or None when there's nothing to count yet."""
    return {"label": label, "value": round(100 * hits / n) if n else None, "unit": "%",
            "hits": hits, "n": n, "definition": definition, "how": how}


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def test_metrics(lab: dict) -> list[dict]:
    tests = lab.get("tests") or []
    intent = [t for t in tests if t.get("intent")]
    security = [t for t in tests if t.get("security")]
    ran = [t for t in tests if t["passed"] + t["failed"]]
    return [
        metric("Test pass rate", lab.get("passed") or 0, lab.get("finished") or 0,
               "Passed runs out of finished runs, latest run of each test (each test runs 3 times)."),
        metric("Passed every run", sum(1 for t in ran if not t["failed"]), len(ran),
               "Tests where all of the latest runs passed. The same AI can answer differently each time, so a "
               "test only counts here if it never failed."),
        metric("Passed at least once", sum(1 for t in ran if t["passed"]), len(ran),
               "Tests where at least one of the latest runs passed. The gap between this and \"Passed every run\" "
               "is tests that pass sometimes and fail sometimes."),
        metric("Intent and priority", sum(t["passed"] for t in intent), sum(t["passed"] + t["failed"] for t in intent),
               "Runs of the tests that check whether the agent read the situation right (emergency or not, "
               "off-topic, unclear) that passed."),
        metric("Holds up against tricks", sum(t["passed"] for t in security),
               sum(t["passed"] + t["failed"] for t in security),
               "Runs of the tests where a caller tries to trick the agent (asks for its instructions, fakes a "
               "system message, pushes for a higher priority, asks for an alarm code or another customer's "
               "details) that passed."),
    ]


def voice_metrics(voice: dict) -> list[dict]:
    """From the voice tests (real audio): numbers heard exactly, and how long the caller waits."""
    if voice.get("status") != "ok":
        return []
    rows = voice.get("numbers") or []
    calls = sum(r["calls"] for r in rows)
    wait = voice["response_time"]["all"]
    return [
        metric("Phone number heard exactly (voice tests)", sum(r["number_heard"] for r in rows), calls,
               "Voice-test calls, in quiet, noise, and over a phone line, where the speech-to-text got all ten digits "
               "of the caller's number right."),
        {"label": "Caller wait (voice tests)", "unit": "ms", "n": wait["n"], "value": wait["typical_ms"],
         "slow": wait["slow_ms"], "how": "measured",
         "definition": "From the end of the caller's last word to the first sound of Sam's reply, timed by the test "
                       "caller: the middle value, and the slowest 10%."},
    ]


def call_metrics(tickets: list[dict], tool_calls: list[dict], calls: dict[str, dict]) -> list[dict]:
    real = [t for t in tickets if not t.get("scenario")]
    emergencies = [t for t in real if t.get("priority") == "emergency"]
    suggested = [t for t in real if t.get("suggested_priority")]

    by_conv: dict[str, list[dict]] = {}
    for r in tool_calls:
        if r.get("conversation_id") and r.get("tool") != "record_follow_up_outcome":
            by_conv.setdefault(r["conversation_id"], []).append(r)
    completed = sum(1 for rows in by_conv.values()
                    if any(r.get("ticket_id") or r.get("tool") in OUTCOME_TOOLS for r in rows))

    graded = {cid: (c.get("evaluation") or {}) for cid, c in calls.items() if c.get("eval_status") == "done"}

    def ai(criterion: str) -> tuple[int, int]:
        hits = n = 0
        for ev in graded.values():
            result = ((ev.get("results") or {}).get(criterion) or {}).get("result")
            if result in ("success", "failure"):
                n += 1
                hits += result == "success"
        return hits, n

    measured = [ev["metrics"] for ev in graded.values() if ev.get("metrics")]
    tools = sum(m.get("tool_calls") or 0 for m in measured)
    tool_errors = sum(m.get("tool_errors") or 0 for m in measured)
    transfers = sum(m.get("transfers") or 0 for m in measured)
    transfer_errors = sum(m.get("transfer_errors") or 0 for m in measured)
    turns = sum(m.get("agent_turns") or 0 for m in measured)
    cut_in = sum(m.get("interrupted") or 0 for m in measured)
    answers = [ms for m in measured for ms in (m.get("answer_ms") or [])]
    costs = [m["cost_usd"] for m in measured if isinstance(m.get("cost_usd"), (int, float))]

    promises, promises_n = ai(evaluation.CRITERION)
    confirmed, confirmed_n = ai(evaluation.CONFIRMED)
    out = [
        metric("Escalation", sum(1 for t in emergencies if t.get("paged_at")), len(emergencies),
               "Emergency tickets where the on-call technician was alerted."),
        metric("Priority matched the rules", sum(1 for t in suggested if t["suggested_priority"] == t.get("priority")),
               len(suggested), "Tickets where the AI's suggested priority matched the final priority our rules set."),
        metric("Tool calls worked", tools - tool_errors, tools,
               "Tool calls (lookups, tickets, alerts, messages) that returned without an error, from ElevenLabs' call records."),
        metric("Handoffs worked", transfers - transfer_errors, transfers,
               "Handoffs to Jordan or Riley that went through without an error."),
        metric("Calls completed", completed, len(by_conv),
               "Calls where Sam used a tool and the call ended with a ticket, message, or sales lead."),
        metric("Avoided unsupported promises", promises, promises_n,
               "Calls graded by ElevenLabs after the call: no promise the tools didn't back up.", how="ai"),
        metric("Confirmed details first", confirmed, confirmed_n,
               "Calls graded by ElevenLabs: name and number read back before any ticket, message, or handoff. "
               "A caller who declines to give a name can still count as a miss here.", how="ai"),
        metric("Caller interruptions", cut_in, turns,
               "Agent replies the caller talked over. A count of how often it happens, not a grade of how Sam recovered."),
    ]
    out.append({"label": "Response time", "unit": "ms", "n": len(answers),
                "value": round(statistics.median(answers)) if answers else None,
                "slow": round(_percentile(answers, 0.9)) if answers else None,
                "definition": "From when the caller stops talking to when the agent's voice starts: the middle value, "
                              "and the slowest 10% (ElevenLabs' own timing).", "how": "measured"})
    out.append({"label": "Cost per call", "unit": "usd", "n": len(costs),
                "value": round(statistics.median(costs), 3) if costs else None,
                "total": round(sum(costs), 2) if costs else None,
                "definition": "ElevenLabs' price for each call (voice plus AI model), the middle value. This is "
                              "ElevenLabs' list price per call, not what the monthly plan charges.", "how": "measured"})
    return out


def _backfill(ids: list[str], calls: dict[str, dict]) -> None:
    """Fill in calls the scorecard can't count yet, a few per page view: calls nobody has opened (so never
    graded), and calls graded before metrics were saved. Newest first, so recent calls show up soonest."""
    if not config.ELEVENLABS_API_KEY:
        return
    todo = [cid for cid in ids
            if (calls.get(cid) or {}).get("eval_status") != "done"
            or "metrics" not in ((calls.get(cid) or {}).get("evaluation") or {})]
    # Never tried first, then graded-without-metrics; calls still pending (or that keep failing) go last,
    # so one stuck call can't block the rest
    rank = {None: 0, "done": 1}
    todo.sort(key=lambda cid: rank.get((calls.get(cid) or {}).get("eval_status"), 2))
    for cid in todo[:BACKFILL_PER_REQUEST]:
        grade = evaluation.fetch_grade(cid, want_metrics=True)
        if grade.get("status") == "done":
            calls[cid] = {**(calls.get(cid) or {}), "eval_status": "done",
                          "evaluation": {"results": grade.get("results") or {}, "metrics": grade.get("metrics")}}


def scorecard(lab: dict | None = None) -> dict:
    if _cache["data"] and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    lab = lab if lab is not None else qa_lab.lab_results()
    data = {"tests": test_metrics(lab) if lab.get("status") == "ok" else [], "calls": []}
    data["tests"] += voice_metrics(voice_lab.summary())
    try:
        store = get_store()
        # Voice-test calls are tests, not real calls
        tickets = [t for t in store.recent_tickets(500) if not voice_lab.is_test(t.get("conversation_id"))]
        tool_calls = [r for r in store.recent_tool_calls(2000) if not voice_lab.is_test(r.get("conversation_id"))]
        ids = list(dict.fromkeys([r["conversation_id"] for r in tool_calls if r.get("conversation_id")]
                                 + [t["conversation_id"] for t in tickets if t.get("conversation_id")]))
        calls = store.calls_by_ids(ids)
        _backfill(ids, calls)
        data["calls"] = call_metrics(tickets, tool_calls, calls)
    except Exception:  # noqa: BLE001 - the lab page should still load
        log.exception("Could not build the Evaluation Lab scorecard")
    _cache.update(at=time.time(), data=data)
    return data
