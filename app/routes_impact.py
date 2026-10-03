"""NightAgent Business Impact: demo metrics counted from the app's own records.

No revenue figures. Time saved is an estimate from real conversations only (live calls and
follow-up calls), using the per-call assumptions below, which the page prints next to it.
"""
from fastapi import APIRouter

from app.store import get_store

router = APIRouter(prefix="/api")

MINUTES_PER_INTAKE_CALL = 6  # answering, account lookup, triage, writing the ticket
MINUTES_PER_FOLLOW_UP = 5    # calling back, confirming the fix, logging the outcome


def _metrics(c: dict) -> dict:
    # Live calls: ones that created a ticket, plus ones that ended in a message, a handoff, or an answer
    without_ticket = c.get("calls_without_ticket", 0)
    live = c["live_calls"] + without_ticket
    calls = live + c["scenario_calls"]
    minutes = live * MINUTES_PER_INTAKE_CALL + c["follow_ups"] * MINUTES_PER_FOLLOW_UP
    return {
        "calls_handled": calls,
        "live_calls": live,
        "calls_without_ticket": without_ticket,
        "specialist_calls": c.get("specialist_calls", 0),
        "scenario_calls": c["scenario_calls"],
        "tickets": c["tickets"],
        "emergencies": c["emergencies"],
        "needed_a_person": c["paged"],
        "handled_without_waking_anyone": max(0, c["tickets"] - c["paged"]),
        "follow_ups": c["follow_ups"],
        "resolved": c["resolved"],
        "reopened": c["reopened"],
        "escalated": c["escalated"],
        "new_from_follow_up": c["new_from_follow_up"],
        "opportunities": c["opportunities"],
        "tasks": c["tasks"],
        "minutes_saved": minutes,
        "assumptions": {
            "minutes_per_intake_call": MINUTES_PER_INTAKE_CALL,
            "minutes_per_follow_up": MINUTES_PER_FOLLOW_UP,
        },
    }


@router.get("/impact")
def impact() -> dict:
    # One cheap database call (ns_impact), so the numbers are always current.
    return _metrics(get_store().impact_counts())
