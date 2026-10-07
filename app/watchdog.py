"""Safety watchdog: every real emergency ticket should have paged the on-call technician, quickly.

Lists live emergencies with no successful page after PAGE_DEADLINE_MINUTES, with the reason the records
show, and times each successful page from ticket to alert. Scripted scenarios never page anyone, so
they're left out, and so are voice-test calls.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from app import metrics, voice_lab
from app.store import get_store

PAGE_DEADLINE_MINUTES = 5


def _secs(a: str, b: str) -> float:
    return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()


def _why(ticket: dict, events: list[dict], tool_calls: list[dict]) -> str:
    """The reason the records give for an emergency with no page. Never a guess."""
    if any(e["event_type"] == "page_failed" for e in events):
        return "The alert was sent but didn't go through, and wasn't retried successfully"
    pages = [t for t in tool_calls if t["tool"] == "page_on_call_tech"]
    if pages:
        return f"Sam asked for an alert, and it wasn't sent: {pages[-1].get('outcome') or 'no result recorded'}"
    if ticket.get("source_ticket_id"):
        return f"Raised on the check-in call for {ticket['source_ticket_id']}; that call has no paging step"
    if not tool_calls:
        return "Sam never asked for an alert (this call came before tool tracking, so the reason isn't recorded)"
    return "Sam never asked for an alert"


def watchdog(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    store = get_store()
    recent = store.recent_tickets(500)
    by_id = {t["ticket_id"]: t for t in recent}
    tickets = [t for t in recent if t.get("priority") == "emergency" and not voice_lab.is_test(t.get("conversation_id"))
               and metrics.source_of_ticket(t, by_id) == metrics.LIVE]

    timings, missed, waiting = [], [], 0
    for t in tickets:
        if t.get("paged_at"):
            timings.append(max(0.0, _secs(t["created_at"], t["paged_at"])))
            continue
        age_min = (now - datetime.fromisoformat(t["created_at"])).total_seconds() / 60
        if age_min < PAGE_DEADLINE_MINUTES:
            waiting += 1
            continue
        convs = [c for c in (t.get("conversation_id"),) if c]
        missed.append({
            "ticket_id": t["ticket_id"],
            "created_at": t["created_at"],
            "status": t.get("status"),
            "reason": _why(t, store.list_events(t["ticket_id"]), store.tool_calls_for(t["ticket_id"], convs)),
        })
    ordered = sorted(timings)
    return {
        "deadline_minutes": PAGE_DEADLINE_MINUTES,
        "emergencies": len(tickets),
        "paged": len(timings),
        "waiting": waiting,
        "missed": sorted(missed, key=lambda m: m["created_at"], reverse=True),
        "ticket_to_page": {
            "n": len(ordered),
            "typical_s": round(statistics.median(ordered)) if ordered else None,
            "slow_s": round(ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))]) if ordered else None,
        },
    }
