"""Demo Mode content: the scenarios a reviewer can pick and the made-up technician roster.

Everything here is fictional and is labeled as simulated wherever it appears.
"""

# Fictional technicians. Not real employees.
TECHNICIANS = {
    "emergency": "Mike Rodriguez",
    "urgent": "Dana Brooks",
    "routine": "Dana Brooks",
}

SCENARIOS = {
    "emergency_resolved": {
        "title": "Emergency, fixed the same night",
        "story": "Main entrance won't unlock. P1 dispatch, technician fixes it, and the customer confirms on the follow-up call.",
        "customer_id": "C-1003",
        "caller_name": "Priya Shah",
        "callback_number": "4245550119",
        "issue_summary": "Main employee entrance will not unlock. About 30 employees on the night shift can't get in, and there's no other entrance with a reader.",
        "category": "entry_blocked",
        "suggested_priority": "urgent",
    },
    "problem_returns": {
        "title": "The problem comes back",
        "story": "Back door won't lock. The technician fixes it, but on the follow-up call the customer says it failed again.",
        "customer_id": "C-1001",
        "caller_name": "Maria Lopez",
        "callback_number": "3105550142",
        "issue_summary": "Back door will not lock while closing up the office for the night.",
        "category": "cannot_secure_site",
        "suggested_priority": "urgent",
    },
    "expansion": {
        "title": "Repair leads to an upgrade",
        "story": "Loading dock readers stop reading badges. After the repair, the customer mentions replacing readers building-wide.",
        "customer_id": "C-1003",
        "caller_name": "Priya Shah",
        "callback_number": "4245550119",
        "issue_summary": "Two badge readers at the loading dock stopped reading employee badges.",
        "category": "access_issue",
        "suggested_priority": "routine",
    },
    "poor_service": {
        "title": "Unhappy with the visit",
        "story": "Cameras stop recording after a power outage. On the follow-up call the customer says it never really worked after the visit.",
        "customer_id": "C-1002",
        "caller_name": "James Carter",
        "callback_number": "3105550178",
        "issue_summary": "Cameras stopped recording after a power outage this evening.",
        "category": "system_offline",
        "suggested_priority": "routine",
    },
}

# Demo-wide limit, so the public page can't be used to flood the database.
SCENARIOS_PER_HOUR = 60


def technician_for(priority: str) -> str:
    return TECHNICIANS.get(priority, TECHNICIANS["routine"])


def public_scenarios() -> list[dict]:
    return [{"id": key, "title": s["title"], "story": s["story"]} for key, s in SCENARIOS.items()]
