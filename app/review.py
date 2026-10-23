"""Human review: which calls a person should look at before the ticket is left to run, and what to do next.

evaluate_review() is pure: it takes the facts in call_data() and returns the verdict, so the rules are easy to
test and edit. Every rule, its severity, its words, and the next-step options live in RULES and SETTINGS below.
The verdict goes onto the Zendesk ticket (app/zendesk.py): the review fields, a tag per reason, and one line in
the private note. It never changes the board ticket; the rules in app/triage.py still own the board's priority.
"""
import re
from datetime import datetime, timedelta, timezone

SEVERITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}

# Order inside a severity is the order here. options[0] is the recommendation.
RULES = {
    "EMERGENCY_UNCLEAR": {"severity": "Critical", "label": "emergency words but not an emergency priority",
                          "options": ["Call back now to check for an emergency", "Page the on-call technician",
                                      "Send SMS asking for details"]},
    "NO_ACCOUNT_MATCH": {"severity": "High", "label": "no matching account or unknown caller",
                         "options": ["Call back to verify identity", "Create the account and dispatch",
                                     "Send SMS asking for details"]},
    "SCORECARD_FAIL": {"severity": "High", "label": "a call check failed or is uncertain",
                       "options": ["Review the transcript and call back", "Approve as-is",
                                   "Send SMS confirming next steps"]},
    "CALLER_WANTS_HUMAN": {"severity": "High", "label": "caller asked for a person or a callback",
                           "options": ["Call back", "Send SMS with a callback time", "Approve as-is"]},
    "PRIORITY_MISMATCH": {"severity": "Medium", "label": "AI priority differs from the rules",
                          "options": ["Confirm the priority and approve", "Call back to check urgency", "Dispatch now"]},
    "NEGATIVE_SENTIMENT": {"severity": "Medium", "label": "caller was frustrated or upset",
                           "options": ["Call back to follow up personally", "Send SMS acknowledging the issue",
                                       "Approve as-is"]},
    "REPEAT_OR_RELATED": {"severity": "Medium", "label": "open or recent ticket for the same caller or account",
                          "options": ["Link it to the related ticket", "Call back to check if it's the same issue",
                                      "Approve as a new issue"]},
    "LOW_CONFIDENCE": {"severity": "Low", "label": "unclear intent or unconfirmed details",
                       "options": ["Review the transcript", "Call back to confirm details", "Approve as-is"]},
}

SETTINGS = {
    # Matched as whole words or phrases in the issue summary and the caller's own lines (never the agent's)
    "emergency_words": ["fire", "smoke", "smoky", "burning", "sparks", "sparking", "melting", "break-in", "break in",
                        "broke in", "breaking in", "intruder", "someone inside", "gas leak", "carbon monoxide",
                        "in danger", "911"],
    # Phrases, not single words: "manager" alone would catch "I'm the store manager", "callback" "my callback number"
    "wants_human_phrases": ["real person", "a human", "live person", "speak to someone", "talk to someone",
                            "speak to a person", "talk to a person", "speak with someone", "talk with someone",
                            "representative", "operator", "speak to a manager", "talk to a manager",
                            "your manager", "a supervisor", "someone call me back", "have someone call",
                            "someone to call me", "can you call me back", "could you call me back",
                            "please call me back"],
    "negative_sentiments": ["frustrated", "upset"],  # "stressed" is normal on a night call, so it doesn't count
    # AI checks that always apply to a call that made a repair ticket, so "unknown" there means uncertain.
    # The others are "unknown" whenever they don't apply (no safety words, no tricks), which is fine.
    "ticket_checks": ["confirmed_details_first", "correct_routing", "clear_close"],
    # Apply only once the ticket is an emergency: then "unknown" is uncertain, and before that even a "failure" is
    # ignored (the grader failed "Emergency handled" on an urgent ticket for not paging, NS-3646)
    "emergency_checks": ["emergency_handled"],
    "related_days": 7,
}

PRIORITY_ORDER = ["routine", "urgent", "emergency"]


def _any(text: str, phrases: list[str]) -> bool:
    """Whole words only: "fire" matches "fire alarm" but not "firewall"."""
    text = " ".join(text.lower().split())
    return any(re.search(rf"(?<![a-z0-9]){re.escape(p.lower())}(?![a-z0-9])", text) for p in phrases)


def evaluate_review(call_data: dict) -> dict:
    """call_data (see call_data() for where each comes from):
      priority, suggested_priority: the rules' final priority and the AI's suggestion (routine/urgent/emergency)
      account_matched, requester_known: bools
      scorecard: {check id: "success" | "failure" | "unknown"} from ElevenLabs' grading
      sentiment, intent, identity_verified: ElevenLabs' analysis, None if not given
      issue, caller_text: the issue summary and the caller's lines of the transcript
      related_tickets: count of open or recent tickets for the same caller or account
    Returns {"reviewNeeded", "reasons": [{"code", "severity"}], "options": [str], "bump_priority": bool}."""
    found = []
    priority, suggested = call_data.get("priority"), call_data.get("suggested_priority")
    said = f"{call_data.get('issue') or ''}\n{call_data.get('caller_text') or ''}"

    if priority != "emergency" and _any(said, SETTINGS["emergency_words"]):
        found.append("EMERGENCY_UNCLEAR")
    if not call_data.get("account_matched") or not call_data.get("requester_known"):
        found.append("NO_ACCOUNT_MATCH")
    scorecard = call_data.get("scorecard") or {}
    emergency = priority == "emergency"
    if not emergency:
        scorecard = {c: r for c, r in scorecard.items() if c not in SETTINGS["emergency_checks"]}
    must_apply = SETTINGS["ticket_checks"] + (SETTINGS["emergency_checks"] if emergency else [])
    if any(r == "failure" for r in scorecard.values()) or \
            any(scorecard.get(c) not in ("success", "failure") for c in must_apply if c in scorecard):
        found.append("SCORECARD_FAIL")
    if _any(call_data.get("caller_text") or "", SETTINGS["wants_human_phrases"]):
        found.append("CALLER_WANTS_HUMAN")
    if suggested and priority and suggested != priority:
        found.append("PRIORITY_MISMATCH")
    if call_data.get("sentiment") in SETTINGS["negative_sentiments"]:
        found.append("NEGATIVE_SENTIMENT")
    if call_data.get("related_tickets"):
        found.append("REPEAT_OR_RELATED")
    # Not ElevenLabs' overall call_successful: it marked a call that went fine a failure (NS-3646)
    if call_data.get("intent") == "unclear" or call_data.get("identity_verified") is False:
        found.append("LOW_CONFIDENCE")

    order = list(RULES)
    found.sort(key=lambda c: (SEVERITY_RANK[RULES[c]["severity"]], order.index(c)))
    return {
        "reviewNeeded": bool(found),
        "reasons": [{"code": c, "severity": RULES[c]["severity"]} for c in found],
        "options": list(RULES[found[0]]["options"]) if found else [],
        "bump_priority": "EMERGENCY_UNCLEAR" in found,
    }


def note_line(review: dict) -> str | None:
    """The line added to the Zendesk ticket's private note."""
    if not review["reviewNeeded"]:
        return None
    reasons = ", ".join(f"{r['code']} ({RULES[r['code']]['label']})" for r in review["reasons"])
    return f"Needs review: {reasons}. Suggested: {'; '.join(review['options'])}."


def options_text(review: dict) -> str:
    """The Recommended options field: numbered, first one marked."""
    return "\n".join(f"{i}. {o}{' (recommended)' if i == 1 else ''}" for i, o in enumerate(review["options"], 1))


def caller_lines(transcript: str | None) -> str:
    return "\n".join(line.removeprefix("Caller: ") for line in (transcript or "").splitlines()
                     if line.startswith("Caller: "))


def related_tickets(ticket: dict, store) -> int:
    """Other open tickets, or any from the last few days, for the same account (or, without an account, the
    same callback number). Tickets from this same call don't count."""
    since = (datetime.now(timezone.utc) - timedelta(days=SETTINGS["related_days"])).isoformat()
    if ticket.get("customer_id"):
        others = store.tickets_for_customer(ticket["customer_id"], limit=20)
    else:
        others = [t for t in store.recent_tickets(200) if not t.get("customer_id") and not t.get("scenario")
                  and ticket.get("callback_number") and t.get("callback_number") == ticket["callback_number"]]
    return sum(1 for t in others
               if t["ticket_id"] != ticket["ticket_id"]
               and (not ticket.get("conversation_id") or t.get("conversation_id") != ticket["conversation_id"])
               and (t.get("status") not in ("resolved", "closed") or (t.get("created_at") or "") >= since))


def call_data(ticket: dict, analysis: dict | None, store) -> dict:
    """The facts evaluate_review() needs, from the board ticket, the analyzed call (evaluation.analyze), and the store."""
    from app.routes_tools import given  # here, since routes_tools imports zendesk, which imports this module
    from app.triage import normalize_priority
    analysis = analysis or {}
    data = analysis.get("data") or {}
    return {
        "priority": ticket.get("priority"),
        # Normalized the way triage reads it, so "High" vs "urgent" isn't a false mismatch
        "suggested_priority": normalize_priority(ticket["suggested_priority"]) if ticket.get("suggested_priority") else None,
        "account_matched": bool(ticket.get("customer_id")),
        "requester_known": bool(given(ticket.get("caller_name"), 100)),
        "scorecard": {k: (v or {}).get("result") for k, v in (analysis.get("results") or {}).items()},
        "sentiment": data.get("caller_sentiment"),
        "intent": data.get("intent"),
        "identity_verified": data.get("identity_verified"),
        "issue": ticket.get("issue_summary"),
        "caller_text": caller_lines(analysis.get("transcript")),
        "related_tickets": related_tickets(ticket, store),
    }
