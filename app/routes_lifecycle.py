"""Public endpoints for the ticket timeline and Demo Mode.

Demo Mode compresses hours of real dispatch work into a few clicks. Everything it adds is
written as a simulated event. Only the browser that started a demo ticket (or whose own call
created it) holds that ticket's demo key, so visitors can't push each other's tickets around.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import logging

from app import config, demo, lifecycle, report
from app.follow_up import follow_up_variables
from app.service import (move_ticket, public_event, public_message, public_opportunity, public_task,
                         public_ticket, record_event, shift)
from app.store import get_store, now_iso
from app.triage import triage

router = APIRouter(prefix="/api")

CLAIM_WINDOW_HOURS = 3


class ScenarioRequest(BaseModel):
    scenario: str = Field(..., max_length=40)


class ClaimRequest(BaseModel):
    ticket_id: str = Field(..., max_length=20)
    conversation_id: str = Field(..., min_length=8, max_length=120)


class VoiceRequest(BaseModel):
    ticket_id: str = Field(..., max_length=20)
    conversation_id: str = Field(..., min_length=8, max_length=120)
    voice: str = Field(..., max_length=20)


class DemoKeyRequest(BaseModel):
    ticket_id: str = Field(..., max_length=20)
    demo_key: str = Field(..., min_length=16, max_length=80)


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _new_key() -> tuple[str, str]:
    key = secrets.token_urlsafe(24)
    return key, _hash(key)


def _ticket_or_404(ticket_id: str) -> dict:
    ticket = get_store().get_ticket(ticket_id.strip().upper())
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found.")
    return ticket


def _owned_demo_ticket(req: DemoKeyRequest) -> dict:
    ticket = _ticket_or_404(req.ticket_id)
    stored = ticket.get("demo_key_hash") or ""
    if not ticket.get("demo") or not stored or not hmac.compare_digest(stored, _hash(req.demo_key)):
        raise HTTPException(status_code=403, detail="This ticket can only be advanced from the browser that started it.")
    return ticket


def _detail(ticket: dict) -> dict:
    store = get_store()
    tid = ticket["ticket_id"]
    nxt = lifecycle.next_demo_step(ticket.get("status"))
    events = store.list_events(tid)
    tasks = store.tasks_for(tid)
    opportunities = store.opportunities_for(tid)
    try:
        convs = [c for c in (ticket.get("conversation_id"), ticket.get("follow_up_conversation_id")) if c]
        tool_calls = store.tool_calls_for(tid, convs)
    except Exception:  # noqa: BLE001 - the report is a bonus; the ticket must still load
        logging.getLogger("nightshift").exception("Could not load tool calls for %s", tid)
        tool_calls = []
    return {
        "ticket": public_ticket(ticket),
        "events": [public_event(e) for e in events],
        "tool_calls": [report.public_tool_call(t) for t in tool_calls],
        "report": report.build(ticket, events, tool_calls, tasks, opportunities),
        "next_step": lifecycle.STATE_LABELS[nxt[0]] if nxt else None,
        "follow_up_ready": lifecycle.normalize_state(ticket.get("status")) == "follow_up_pending",
        "actions": {
            "tasks": [public_task(t) for t in tasks],
            "opportunities": [public_opportunity(o) for o in opportunities],
            "tickets": [public_ticket(t) for t in store.linked_tickets(tid)],
        },
    }


@router.get("/tickets/{ticket_id}")
def ticket_detail(ticket_id: str) -> dict:
    return _detail(_ticket_or_404(ticket_id))


@router.get("/messages")
def messages() -> list[dict]:
    """Messages Sam took for a department or a person (calls that weren't a service problem)."""
    return [public_message(t) for t in get_store().recent_messages()]


@router.get("/messages/{message_id}")
def message_detail(message_id: str) -> dict:
    store = get_store()
    task = store.get_task(message_id.strip().upper())
    if not task or task.get("source_ticket_id") or not task.get("source_conversation_id"):
        raise HTTPException(status_code=404, detail="Message not found.")
    try:
        tool_calls = store.tool_calls_for("", [task["source_conversation_id"]])
    except Exception:  # noqa: BLE001
        logging.getLogger("nightshift").exception("Could not load tool calls for %s", message_id)
        tool_calls = []
    msg = public_message(task)
    opp = store.opportunity_for_call(task["source_conversation_id"]) if task.get("destination") == "account_executive" else None
    return {
        "message": msg,
        "tool_calls": [report.public_tool_call(t) for t in tool_calls],
        "report": report.build_message(task, tool_calls, msg["department"], msg["callback_number"],
                                       [opp] if opp else None),
    }


@router.get("/demo/scenarios")
def scenarios() -> list[dict]:
    return demo.public_scenarios()


@router.post("/demo/scenario")
def start_scenario(req: ScenarioRequest) -> dict:
    scenario = demo.SCENARIOS.get(req.scenario)
    if not scenario:
        raise HTTPException(status_code=404, detail="Unknown scenario.")
    store = get_store()
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    if store.count_demo_tickets_since(hour_ago) >= demo.SCENARIOS_PER_HOUR:
        raise HTTPException(status_code=429, detail="The demo is busy right now. Please try again in a few minutes.")

    category, priority, reason = triage(scenario["category"], scenario["suggested_priority"])
    key, key_hash = _new_key()
    ticket = store.create_ticket({
        "customer_id": scenario["customer_id"],
        "caller_name": scenario["caller_name"],
        "callback_number": scenario["callback_number"],
        "issue_summary": scenario["issue_summary"],
        "category": category,
        "priority": priority,
        "priority_reason": reason,
        "status": "awaiting_dispatch",
        "demo": True,
        "scenario": req.scenario,
        "demo_key_hash": key_hash,
        "base_status": "awaiting_dispatch",
    })
    tid, now = ticket["ticket_id"], now_iso()
    customer = store.get_customer(scenario["customer_id"]) or {}
    common = {"simulated": True, "source": "scenario"}
    record_event(tid, "call_received",
                 f"{customer.get('business_name', 'Customer')}: {scenario['issue_summary'][:160]} (simulated call)",
                 occurred_at=shift(now, -4), actor_type="customer", **common)
    record_event(tid, "triage_completed",
                 f"{lifecycle.PRIORITY_LABELS[priority]}: {reason}. Our rules set the priority, not the AI.",
                 occurred_at=shift(now, -1), metadata={"category": category}, **common)
    record_event(tid, "ticket_created", f"{tid} is waiting for a technician.",
                 occurred_at=now, actor_type="agent", **common)
    return {"demo_key": key, **_detail(store.get_ticket(tid))}


@router.post("/demo/claim")
def claim_call_ticket(req: ClaimRequest) -> dict:
    """Turn the ticket your own call just created into a demo ticket you can advance.
    Proof of ownership is the conversation id, which only the caller's browser has."""
    ticket = _ticket_or_404(req.ticket_id)
    if not ticket.get("conversation_id") or not hmac.compare_digest(ticket["conversation_id"], req.conversation_id):
        raise HTTPException(status_code=403, detail="That ticket came from a different call.")
    if ticket.get("demo_key_hash"):
        raise HTTPException(status_code=409, detail="Demo Mode is already running for this ticket.")
    created = datetime.fromisoformat(ticket["created_at"])
    if datetime.now(timezone.utc) - created > timedelta(hours=CLAIM_WINDOW_HOURS):
        raise HTTPException(status_code=403, detail="This call is too old to start Demo Mode.")
    key, key_hash = _new_key()
    base = lifecycle.normalize_state(ticket.get("status"))
    get_store().update_ticket(ticket["ticket_id"], {"demo": True, "demo_key_hash": key_hash, "base_status": base})
    return {"demo_key": key, **_detail(get_store().get_ticket(ticket["ticket_id"]))}


@router.post("/demo/voice")
def note_voice(req: VoiceRequest) -> dict:
    """Remember which voice (or text chat) took the call, for the call report. Same proof as a
    claim: only the caller's browser knows the conversation id."""
    store = get_store()
    record_id = req.ticket_id.strip().upper()
    if record_id.startswith("TASK-"):  # a message rather than a ticket
        record = store.get_task(record_id)
        conv = (record or {}).get("source_conversation_id")
        save = store.update_task
    else:
        record = store.get_ticket(record_id)
        conv = (record or {}).get("conversation_id")
        save = store.update_ticket
    if not record:
        raise HTTPException(status_code=404, detail="Not found.")
    if not conv or not hmac.compare_digest(conv, req.conversation_id):
        raise HTTPException(status_code=403, detail="That record came from a different call.")
    voice = req.voice.strip()
    voice = report.TEXT_CHAT if voice.lower() == report.TEXT_CHAT else voice.capitalize()
    if voice != report.TEXT_CHAT and voice not in report.VOICES:
        raise HTTPException(status_code=400, detail="Unknown voice.")
    if not record.get("voice"):
        save(record_id, {"voice": voice})
    return {"ok": True}


@router.post("/demo/advance")
def advance(req: DemoKeyRequest) -> dict:
    ticket = _owned_demo_ticket(req)
    step = lifecycle.next_demo_step(ticket.get("status"))
    if not step:
        raise HTTPException(status_code=409, detail="This ticket is at the end of the demo path.")
    target, event_type, minutes = step

    events = get_store().list_events(ticket["ticket_id"])
    last = events[-1]["occurred_at"] if events else ticket["created_at"]
    extra, description = {}, lifecycle.EVENT_LABELS[event_type]
    if target == "technician_assigned" and ticket.get("paged_at"):
        # The call already paged the on-call technician, so that's who takes the job.
        tech = config.ONCALL_TECH_NAME
        extra["technician_name"] = tech
        description = f"{tech} (the on-call technician who was alerted) takes the job"
    elif target == "technician_assigned":
        tech = demo.technician_for(ticket["priority"])
        extra["technician_name"] = tech
        description = f"{tech} assigned (fictional demo technician)"
    elif target == "dispatched":
        description = f"The service team was told about this {lifecycle.PRIORITY_LABELS.get(ticket['priority'], ticket['priority']).lower()} problem"
    elif target == "follow_up_pending":
        description = "NightAgent will call the customer to make sure it's fixed"
    elif ticket.get("technician_name"):
        description = f"{ticket['technician_name']}: {lifecycle.EVENT_LABELS[event_type].lower()}"

    ticket = move_ticket(ticket, target, extra)
    record_event(ticket["ticket_id"], event_type, description, simulated=True, source="demo",
                 occurred_at=shift(last, minutes), actor_type="demo")
    return _detail(get_store().get_ticket(ticket["ticket_id"]))


@router.post("/demo/follow-up")
def start_follow_up(req: DemoKeyRequest) -> dict:
    """Hand the page what it needs to start NightAgent's follow-up call: the agent id and the
    ticket context, plus a single-use pass the agent sends back with the outcome."""
    ticket = _owned_demo_ticket(req)
    if lifecycle.normalize_state(ticket.get("status")) != "follow_up_pending":
        raise HTTPException(status_code=409, detail="This ticket isn't ready for a follow-up call.")
    if not config.FOLLOWUP_AGENT_ID:
        raise HTTPException(status_code=503, detail="Follow-up calls aren't switched on yet.")
    store = get_store()
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    if store.count_follow_ups_since(hour_ago) >= config.FOLLOW_UPS_PER_HOUR:
        raise HTTPException(status_code=429, detail="The demo is busy right now. Please try again in a few minutes.")
    token, token_hash = _new_key()
    store.update_ticket(ticket["ticket_id"], {"follow_up_token_hash": token_hash, "follow_up_started_at": now_iso()})
    record_event(ticket["ticket_id"], "follow_up_started", "NightAgent is calling the customer to confirm the fix",
                 source="follow_up", actor_type="agent")
    return {"agent_id": config.FOLLOWUP_AGENT_ID, "dynamic_variables": follow_up_variables(ticket, token)}


@router.post("/demo/reset")
def reset(req: DemoKeyRequest) -> dict:
    """Undo every Advance Demo step. The original call or scenario events stay."""
    ticket = _owned_demo_ticket(req)
    if ticket.get("resolution"):
        raise HTTPException(status_code=409, detail="The follow-up call is on record, so this ticket's history is final. Start a new scenario to run it again.")
    store = get_store()
    store.delete_events(ticket["ticket_id"], "demo")
    store.delete_events(ticket["ticket_id"], "follow_up")  # only "call started" rows; no outcome yet
    store.update_ticket(ticket["ticket_id"], {
        "status": ticket.get("base_status") or "awaiting_dispatch",
        "technician_name": None,
        "follow_up_token_hash": None,
    })
    return _detail(store.get_ticket(ticket["ticket_id"]))
