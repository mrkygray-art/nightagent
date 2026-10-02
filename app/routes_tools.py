"""Server tools the voice agent calls in the middle of a conversation.

ElevenLabs POSTs JSON to these endpoints and reads our JSON response back into the
conversation, so responses are short, plain, and tell the agent what to do next.
Tool calls time out after about 20 seconds, so keep these fast.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import hashlib
from datetime import datetime, timedelta, timezone

from app import config, lifecycle
from app.follow_up import DEPARTMENT_LABELS, DESTINATIONS, apply_outcome
from app.notify import page_on_call
from app.security import require_tool_secret
from app.service import log_tool_call, move_ticket, record_event
from app.store import get_store, now_iso, phone_digits
from app.triage import triage

router = APIRouter(prefix="/tools", dependencies=[Depends(require_tool_secret)])


class LookupRequest(BaseModel):
    query: str = Field(..., description="Phone number or business/contact name")
    conversation_id: str | None = Field(None, max_length=120)


class CreateTicketRequest(BaseModel):
    customer_id: str | None = None
    caller_name: str
    callback_number: str
    issue_summary: str
    category: str | None = "other"
    suggested_priority: str | None = "routine"
    conversation_id: str | None = None


class MessageRequest(BaseModel):
    department: str = Field(..., max_length=40)
    reason: str = Field(..., max_length=600)
    caller_name: str = Field(..., max_length=100)
    callback_number: str = Field(..., max_length=40)
    customer_id: str | None = Field(None, max_length=20)
    person_requested: str | None = Field(None, max_length=100)
    best_time: str | None = Field(None, max_length=120)
    ticket_id: str | None = Field(None, max_length=20)
    conversation_id: str | None = Field(None, max_length=120)


class PageRequest(BaseModel):
    ticket_id: str


class FollowUpOutcomeRequest(BaseModel):
    follow_up_token: str = Field(..., max_length=80)
    conversation_id: str | None = Field(None, max_length=120)
    resolution: str = Field(..., max_length=30)
    customer_comments: str | None = Field(None, max_length=1000)
    satisfaction: int | None = None
    current_category: str | None = Field(None, max_length=40)
    suggested_priority: str | None = Field(None, max_length=20)
    current_impact: str | None = Field(None, max_length=400)
    new_issue_summary: str | None = Field(None, max_length=600)
    new_issue_category: str | None = Field(None, max_length=40)
    new_issue_priority: str | None = Field(None, max_length=20)
    sales_interest: str | None = Field(None, max_length=600)
    sales_type: str | None = Field(None, max_length=120)
    sales_scope: str | None = Field(None, max_length=300)
    sales_device_count: str | None = Field(None, max_length=60)
    sales_timeline: str | None = Field(None, max_length=120)
    sales_budget: str | None = Field(None, max_length=120)
    callback_department: str | None = Field(None, max_length=40)
    callback_reason: str | None = Field(None, max_length=400)

FOLLOW_UP_TOKEN_MINUTES = 30

# How Sam introduces the person who will call back
ROLE_PHRASE = {"account_executive": ", your account executive,", "billing": " from billing",
               "service_manager": ", our service manager,"}

# Said back to the agent after every lookup, because the model tends to skip the read-back once
# it knows the problem. Tool results steer it more reliably than the prompt alone.
CONFIRM_FIRST = ("Find out what the caller needs, if you don't know yet: a problem with their system "
                 "(what is happening and when it started), or a message for a department or person. Then, "
                 "before calling create_ticket or take_message, ask for the caller's full name if you don't "
                 "have it, read their name and callback number back (number in groups of three, three, four), "
                 "and wait for them to say it's right. Do not call either tool until they confirm. For a "
                 "message, also ask once, before take_message, if there's a good time to call them back.")


def _public_customer(c: dict) -> dict:
    return {
        "customer_id": c["customer_id"],
        "business_name": c["business_name"],
        "contact_name": c.get("contact_name"),
        "site_address": c.get("site_address"),
        "systems": c.get("systems"),
        "service_plan": c.get("service_plan"),
        "after_hours_coverage": bool(c.get("after_hours_coverage")),
    }


@router.post("/lookup-customer")
def lookup_customer(req: LookupRequest) -> dict:
    started = now_iso()
    matches = get_store().find_customers(req.query)
    outcome = ("Found " + matches[0]["business_name"] if len(matches) == 1
               else f"{len(matches)} possible accounts" if matches else "No matching account")
    log_tool_call("lookup_customer", outcome, conversation_id=req.conversation_id, called_at=started)
    if len(matches) == 1:
        return {"found": True, "customer": _public_customer(matches[0]), "next_step": CONFIRM_FIRST}
    if len(matches) > 1:
        return {
            "found": False,
            "possible_matches": [m["business_name"] for m in matches],
            "message": "More than one account matches. Ask the caller which business they're calling about.",
        }
    return {
        "found": False,
        "message": "No account found. Ask once more for the phone number on the account; "
                   "if still not found, continue without a customer_id.",
        "next_step": CONFIRM_FIRST,
    }


@router.post("/create-ticket")
def create_ticket(req: CreateTicketRequest) -> dict:
    started = now_iso()
    store = get_store()
    category, priority, reason = triage(req.category, req.suggested_priority)

    customer = store.get_customer(req.customer_id) if req.customer_id else None
    ticket = store.create_ticket({
        "customer_id": customer["customer_id"] if customer else None,
        "caller_name": req.caller_name.strip(),
        "callback_number": phone_digits(req.callback_number) or req.callback_number.strip(),
        "issue_summary": req.issue_summary.strip(),
        "category": category,
        "priority": priority,
        "priority_reason": reason,
        "conversation_id": req.conversation_id,
        "status": "awaiting_dispatch",
    })

    tid, conv = ticket["ticket_id"], req.conversation_id
    log_tool_call("create_ticket", f"{tid} created, {lifecycle.PRIORITY_LABELS[priority].lower()}",
                  conversation_id=conv, ticket_id=tid, called_at=started)
    who = customer["business_name"] if customer else "Caller without a matching account"
    record_event(tid, "call_received", f"{who}: {ticket['issue_summary'][:160]}",
                 conversation_id=conv, actor_type="customer")
    record_event(tid, "triage_completed",
                 f"{lifecycle.PRIORITY_LABELS[priority]}: {reason}. Our rules set the priority, not the AI.",
                 conversation_id=conv, actor_type="system", metadata={"category": category})
    record_event(tid, "ticket_created", f"{tid} is waiting for a technician.",
                 conversation_id=conv, actor_type="agent")

    # Billing is decided here, not by the model: only an emergency for a known account whose plan
    # doesn't include after-hours service gets the after-hours rate note.
    mention_billing = priority == "emergency" and bool(customer) and not customer.get("after_hours_coverage")
    if priority == "emergency":
        next_step = "This is an emergency. Call page_on_call_tech now with this ticket_id."
        next_step += (" Their plan does not include after-hours service: when you give the ticket details, say once "
                      "that after-hours dispatch is billed at the after-hours rate under their plan."
                      if mention_billing else " Do not mention billing or rates.")
    elif priority == "urgent":
        next_step = "Tell the caller this is first in the queue for the morning crew, and they'll get a call when the office opens."
    else:
        next_step = "Tell the caller the office will follow up during business hours."

    digits = ticket["ticket_id"].split("-")[1]
    return {
        "ticket_id": ticket["ticket_id"],
        "ticket_number_spoken": "N S " + " ".join(digits),
        "priority": priority,
        "priority_reason": reason,
        "mention_billing": mention_billing,
        "next_step": next_step,
    }


@router.post("/take-message")
def take_message(req: MessageRequest) -> dict:
    """The front desk: the caller wants a department or a person, not (only) a repair. Code decides
    who gets the message and what the caller is told; the agent just collects the details."""
    started = now_iso()
    store = get_store()
    dept = req.department.strip().lower()
    if dept not in DESTINATIONS:
        dept = "service"  # only known teams can receive messages
    customer = store.get_customer(req.customer_id) if req.customer_id else None
    ticket = store.get_ticket(req.ticket_id.strip().upper()) if req.ticket_id else None
    reason = " ".join(req.reason.split())[:600]
    best_time = " ".join((req.best_time or "").split())[:120] or None
    who = DESTINATIONS[dept]
    # A second message to the same person on the same call (say, the caller added a good time to
    # call back) updates the first one rather than leaving two.
    earlier = store.message_for_call(req.conversation_id, dept) if req.conversation_id else None
    if earlier:
        fields = {"summary": reason or earlier.get("summary"),
                  "best_time": best_time or earlier.get("best_time"),
                  "person_requested": " ".join((req.person_requested or "").split())[:100] or earlier.get("person_requested"),
                  "callback_number": phone_digits(req.callback_number) or earlier.get("callback_number")}
        fields["requested_follow_up"] = "Call the caller back" + (f" ({fields['best_time']})" if fields["best_time"] else "")
        store.update_task(earlier["task_id"], fields)
        best_time = fields["best_time"]
        log_tool_call("take_message", f"{earlier['task_id']} updated for {who}", conversation_id=req.conversation_id,
                      ticket_id=earlier.get("source_ticket_id"), called_at=started)
        return _message_reply(earlier["task_id"], dept, who, best_time)
    task = store.create_task({
        "destination": dept,
        "assigned_to": who,
        "customer_id": customer["customer_id"] if customer else None,
        "contact_name": req.caller_name.strip(),
        "site_address": (customer or {}).get("site_address"),
        "source_ticket_id": ticket["ticket_id"] if ticket else None,
        "source_conversation_id": req.conversation_id,
        "reason": f"Message for {DEPARTMENT_LABELS[dept]}",
        "summary": reason,
        "priority": "high" if dept == "service_manager" else "normal",
        "requested_follow_up": "Call the caller back" + (f" ({best_time})" if best_time else ""),
        "callback_number": phone_digits(req.callback_number) or req.callback_number.strip(),
        "person_requested": " ".join((req.person_requested or "").split())[:100] or None,
        "best_time": best_time,
        "demo": bool(ticket and ticket.get("demo")),
    })
    log_tool_call("take_message", f"{task['task_id']} for {who}", conversation_id=req.conversation_id,
                  ticket_id=ticket["ticket_id"] if ticket else None, called_at=started)
    if ticket:
        record_event(ticket["ticket_id"], "task_created", f"{task['task_id']} for {who}: {reason[:160]}",
                     conversation_id=req.conversation_id, actor_type="agent",
                     metadata={"task_id": task["task_id"], "destination": dept})
    return _message_reply(task["task_id"], dept, who, best_time)


def _message_reply(task_id: str, dept: str, who: str, best_time: str | None) -> dict:
    name = who.split(",")[0].replace(" (fictional)", "")
    speaker = f"Our {name.lower()}" if name.endswith("desk") else name + ROLE_PHRASE.get(dept, "")
    when = f" {best_time}" if best_time else " on the next business day"
    return {
        "saved": True,
        "message_id": task_id,
        "tell_the_caller": f"{speaker} will get your message and call you back{when}.",
        "next_step": "Tell the caller who will call them back and when, in one or two sentences. "
                     "Don't promise an exact time beyond that. If the caller then gives a good time to call "
                     "back, or changes their number or reason, call take_message again with the same "
                     "department and the new details: it updates this same message, it doesn't send a "
                     "second one. Never say you've noted something without calling the tool. "
                     "Then ask if there's anything else.",
    }


@router.post("/page-on-call")
def page_on_call_tech(req: PageRequest) -> dict:
    started = now_iso()
    store = get_store()
    ticket = store.get_ticket(req.ticket_id.strip().upper())
    if not ticket:
        return {"paged": False, "message": "Ticket not found. Double-check the ticket_id."}

    def note(outcome: str) -> None:
        log_tool_call("page_on_call_tech", outcome, conversation_id=ticket.get("conversation_id"),
                      ticket_id=ticket["ticket_id"], called_at=started)

    # Guardrail: only emergencies wake someone up, regardless of what the model asks for.
    if ticket["priority"] != "emergency":
        note("Not sent: the rules say this isn't an emergency")
        return {
            "paged": False,
            "message": f"Ticket is {ticket['priority']}, not an emergency, so no page was sent. "
                       "Explain the follow-up timing instead.",
        }
    if ticket.get("paged_at"):
        note("Already alerted earlier")
        return {"paged": True, "message": "The technician was already paged for this ticket."}

    customer = store.get_customer(ticket["customer_id"]) if ticket.get("customer_id") else None
    who = customer["business_name"] if customer else ticket["caller_name"]
    body = (
        f"[NightShift] EMERGENCY {ticket['ticket_id']} - {who}: "
        f"{ticket['issue_summary'][:140]} | Callback {ticket['callback_number']}"
    )
    result = page_on_call(body)
    paged_at = now_iso()
    if lifecycle.can_transition(ticket.get("status"), "dispatched"):
        move_ticket(ticket, "dispatched", {"paged_at": paged_at})
    else:
        store.update_ticket(ticket["ticket_id"], {"paged_at": paged_at})
    simulated = bool(result.get("simulated"))
    note(f"{config.ONCALL_TECH_NAME} alerted" + (" (simulated)" if simulated else ""))
    record_event(ticket["ticket_id"], "technician_paged",
                 f"{config.ONCALL_TECH_NAME} alerted" + (" (simulated: no real text was sent)" if simulated else ""),
                 simulated=simulated, conversation_id=ticket.get("conversation_id"), actor_type="agent")

    return {
        "paged": True,
        "technician_name": config.ONCALL_TECH_NAME,
        "callback_within_minutes": config.CALLBACK_WINDOW_MINUTES,
        "simulated": result.get("simulated", False),
        "message": f"{config.ONCALL_TECH_NAME} has been paged and will call the caller back "
                   f"within {config.CALLBACK_WINDOW_MINUTES} minutes.",
    }


@router.post("/follow-up-outcome")
def follow_up_outcome(req: FollowUpOutcomeRequest) -> dict:
    """Called once by the follow-up agent near the end of the call. The pass proves which ticket
    this call is about; code decides everything that happens next."""
    started = now_iso()
    store = get_store()
    token_hash = hashlib.sha256(req.follow_up_token.strip().encode()).hexdigest()
    ticket = store.find_ticket_by_follow_up_token(token_hash) if req.follow_up_token.strip() else None
    started = ticket and ticket.get("follow_up_started_at")
    fresh = started and datetime.now(timezone.utc) - datetime.fromisoformat(started) < timedelta(minutes=FOLLOW_UP_TOKEN_MINUTES)
    if not ticket or not fresh or lifecycle.normalize_state(ticket.get("status")) != "follow_up_pending":
        return {
            "recorded": False,
            "message": "This follow-up couldn't be saved. Tell the customer the service desk will call them to confirm everything, then close the call.",
        }
    log_tool_call("record_follow_up_outcome", f"Saved: {req.resolution.replace('_', ' ')}",
                  conversation_id=req.conversation_id, ticket_id=ticket["ticket_id"], called_at=started)
    result = apply_outcome(ticket, req.model_dump(), req.conversation_id)
    return {
        "recorded": True,
        "ticket_id": ticket["ticket_id"],
        "tell_the_customer": " ".join(result["said"]),
        "message": "Saved. Tell the customer what happens next in one or two sentences, then close the call warmly.",
    }
