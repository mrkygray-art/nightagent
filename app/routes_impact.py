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
    calls = c["live_calls"] + c["scenario_calls"]
    minutes = c["live_calls"] * MINUTES_PER_INTAKE_CALL + c["follow_ups"] * MINUTES_PER_FOLLOW_UP
    return {
        "calls_handled": calls,
        "live_calls": c["live_calls"],
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
