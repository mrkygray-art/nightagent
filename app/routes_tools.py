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
from app.follow_up import apply_outcome
from app.notify import page_on_call
from app.security import require_tool_secret
from app.service import move_ticket, record_event
from app.store import get_store, now_iso, phone_digits
from app.triage import triage

router = APIRouter(prefix="/tools", dependencies=[Depends(require_tool_secret)])


class LookupRequest(BaseModel):
    query: str = Field(..., description="Phone number or business/contact name")


class CreateTicketRequest(BaseModel):
    customer_id: str | None = None
    caller_name: str
    callback_number: str
    issue_summary: str
    category: str | None = "other"
    suggested_priority: str | None = "routine"
    conversation_id: str | None = None


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
    matches = get_store().find_customers(req.query)
    if len(matches) == 1:
        return {"found": True, "customer": _public_customer(matches[0])}
    if len(matches) > 1:
        return {
            "found": False,
            "possible_matches": [m["business_name"] for m in matches],
            "message": "More than one account matches. Ask the caller which business they're calling about.",
        }
    return {
        "found": False,
        "message": "No account found. Ask once more for the phone number on the account; "
                   "if still not found, continue and create the ticket without a customer_id.",
    }


@router.post("/create-ticket")
def create_ticket(req: CreateTicketRequest) -> dict:
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
    who = customer["business_name"] if customer else "Caller without a matching account"
    record_event(tid, "call_received", f"{who}: {ticket['issue_summary'][:160]}",
                 conversation_id=conv, actor_type="customer")
    record_event(tid, "triage_completed",
                 f"{lifecycle.PRIORITY_LABELS[priority]}: {reason}. Set by the priority rules, not the AI.",
                 conversation_id=conv, actor_type="system", metadata={"category": category})
    record_event(tid, "ticket_created", f"{tid} created. Awaiting dispatch.",
                 conversation_id=conv, actor_type="agent")

    if priority == "emergency":
        next_step = "This is an emergency. Call page_on_call_tech now with this ticket_id."
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
        "after_hours_coverage": bool(customer and customer.get("after_hours_coverage")),
        "next_step": next_step,
    }


@router.post("/page-on-call")
def page_on_call_tech(req: PageRequest) -> dict:
    store = get_store()
    ticket = store.get_ticket(req.ticket_id.strip().upper())
    if not ticket:
        return {"paged": False, "message": "Ticket not found. Double-check the ticket_id."}

    # Guardrail: only emergencies wake someone up, regardless of what the model asks for.
    if ticket["priority"] != "emergency":
        return {
            "paged": False,
            "message": f"Ticket is {ticket['priority']}, not an emergency, so no page was sent. "
                       "Explain the follow-up timing instead.",
        }
    if ticket.get("paged_at"):
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
    record_event(ticket["ticket_id"], "technician_paged",
                 f"{config.ONCALL_TECH_NAME} paged" + (" (simulated: no real text was sent)" if simulated else ""),
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
    result = apply_outcome(ticket, req.model_dump(), req.conversation_id)
    return {
        "recorded": True,
        "ticket_id": ticket["ticket_id"],
        "tell_the_customer": " ".join(result["said"]),
        "message": "Saved. Tell the customer what happens next in one or two sentences, then close the call warmly.",
    }
