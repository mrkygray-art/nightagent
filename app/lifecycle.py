"""Service ticket lifecycle: the allowed states, the allowed moves between them, and the
demo path that Demo Mode steps through.

Like triage, this is plain code on purpose. The AI never moves a ticket; it only gathers
information. Every move is checked against TRANSITIONS and written as an event, so the
history is never overwritten.
"""

STATES = [
    "new",
    "awaiting_dispatch",
    "dispatched",
    "technician_assigned",
    "en_route",
    "onsite",
    "work_completed",
    "follow_up_pending",
    "resolved",
    "reopened",
    "escalated",
    "closed",
]

# Tickets created before the lifecycle existed used "open"; treat it as awaiting dispatch.
LEGACY_STATES = {"open": "awaiting_dispatch"}

# What customers see. Plain, everyday words; the technical state names stay in code.
STATE_LABELS = {
    "new": "New",
    "awaiting_dispatch": "Waiting for a technician",
    "dispatched": "Technician notified",
    "technician_assigned": "Technician assigned",
    "en_route": "Technician on the way",
    "onsite": "Technician has arrived",
    "work_completed": "Repair finished",
    "follow_up_pending": "Check-in call next",
    "resolved": "Fixed",
    "reopened": "Problem came back",
    "escalated": "Passed to a manager",
    "closed": "Closed: fixed",
}

TRANSITIONS = {
    "new": {"awaiting_dispatch"},
    "awaiting_dispatch": {"dispatched", "technician_assigned"},
    "dispatched": {"technician_assigned"},
    "technician_assigned": {"en_route"},
    "en_route": {"onsite"},
    "onsite": {"work_completed"},
    "work_completed": {"follow_up_pending"},
    "follow_up_pending": {"resolved", "reopened", "escalated"},
    "resolved": {"closed", "reopened"},
    "reopened": {"awaiting_dispatch", "escalated"},
    "escalated": {"technician_assigned", "closed"},
    "closed": {"reopened"},
}

# What Advance Demo does next from each state, and the event it writes. Minutes are the
# demo clock: how long after the previous step this would plausibly happen in real life.
DEMO_STEPS = {
    "awaiting_dispatch": ("dispatched", "dispatch_notified", 2),
    "dispatched": ("technician_assigned", "technician_assigned", 15),
    "technician_assigned": ("en_route", "technician_en_route", 6),
    "en_route": ("onsite", "technician_onsite", 27),
    "onsite": ("work_completed", "work_completed", 43),
    "work_completed": ("follow_up_pending", "follow_up_ready", 9 * 60),
}

EVENT_LABELS = {
    "call_received": "Customer called NightAgent",
    "triage_completed": "Problem saved",
    "ticket_created": "Ticket created",
    "technician_paged": "On-call technician alerted",
    "dispatch_notified": "Technician notified",
    "technician_assigned": "Technician assigned",
    "technician_en_route": "Technician on the way",
    "technician_onsite": "Technician has arrived",
    "work_completed": "Repair finished",
    "follow_up_ready": "Check-in call coming",
    "follow_up_started": "NightAgent called to check in",
    "follow_up_completed": "Check-in call finished",
    "csat_recorded": "Rating saved",
    "resolution_confirmed": "Customer said it's fixed",
    "ticket_closed": "Ticket closed",
    "ticket_reopened": "Problem came back",
    "priority_reviewed": "Priority checked again",
    "ticket_escalated": "Passed to a manager",
    "follow_up_unclear": "A person will call",
    "new_ticket_created": "New problem saved",
    "opportunity_identified": "Upgrade interest passed to sales",
    "task_created": "Someone will follow up",
}

PRIORITY_LABELS = {"emergency": "High priority", "urgent": "Medium priority", "routine": "Normal priority"}


class TransitionError(ValueError):
    pass


def normalize_state(status: str | None) -> str:
    status = (status or "new").strip().lower()
    return LEGACY_STATES.get(status, status if status in TRANSITIONS else "new")


def can_transition(current: str | None, target: str) -> bool:
    return target in TRANSITIONS.get(normalize_state(current), set())


def check_transition(current: str | None, target: str) -> str:
    """Return the normalized current state, or raise if the move isn't allowed."""
    state = normalize_state(current)
    if target not in TRANSITIONS.get(state, set()):
        raise TransitionError(f"A ticket can't go from {state} to {target}.")
    return state


def next_demo_step(status: str | None) -> tuple[str, str, int] | None:
    """(next_state, event_type, demo_minutes) for Advance Demo, or None at the end of the path."""
    return DEMO_STEPS.get(normalize_state(status))
