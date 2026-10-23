"""Sam on Deepgram: the /deepgram call page and the three endpoints behind it (see app/deepgram_voice.py).

POST /api/deepgram/session  a short-lived Deepgram token, the agent Settings, and a signed session for this call
POST /api/deepgram/tool     one of Sam's functions, run by the same code ElevenLabs Sam's tools use
POST /api/deepgram/end      the finished call: transcript stored, summary and sentiment from Deepgram, Zendesk sync

The session limits live in memory, so on serverless hosting they are per instance (like app/notify.py's SMS limit).
"""
import json
import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app import config, deepgram_voice as dg, evaluation, routes_tools as tools, zendesk
from app.deepgram_page import DEEPGRAM_HTML
from app.service import call_ref
from app.store import get_store

router = APIRouter()
log = logging.getLogger("nightshift")

HOUR = 3600
_all_calls: deque = deque()
_calls_by_ip: dict[str, deque] = defaultdict(deque)
_tool_calls: dict[str, int] = defaultdict(int)
_ended: set[str] = set()

# Sam's functions: the request model each one takes and the tool code that runs it
TOOLS = {
    "lookup_customer": (tools.LookupRequest, tools.lookup_customer),
    "create_ticket": (tools.CreateTicketRequest, tools.create_ticket),
    "take_message": (tools.MessageRequest, tools.take_message),
    "check_ticket_status": (tools.TicketStatusRequest, tools.ticket_status),
    "add_ticket_note": (tools.TicketNoteRequest, tools.ticket_note),
    "page_on_call_tech": (tools.PageRequest, tools.page_on_call_tech),
}


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")  # set by Vercel
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _take_slot(ip: str, now: float) -> bool:
    for hits in (_all_calls, _calls_by_ip[ip]):
        while hits and hits[0] <= now - HOUR:
            hits.popleft()
    if len(_all_calls) >= config.DEEPGRAM_CALLS_PER_HOUR or len(_calls_by_ip[ip]) >= config.DEEPGRAM_CALLS_PER_IP_HOUR:
        return False
    _all_calls.append(now)
    _calls_by_ip[ip].append(now)
    return True


def _session(session: str) -> str:
    conv = dg.check_session(session)
    if not conv:
        raise HTTPException(status_code=401, detail="This call has ended. Start a new one.")
    return conv


@router.get("/deepgram", response_class=HTMLResponse)
def deepgram_page() -> str:
    return DEEPGRAM_HTML


@router.post("/api/deepgram/session")
def start_session(request: Request) -> dict:
    if not dg.configured():
        raise HTTPException(status_code=503, detail="Sam on Deepgram isn't set up yet.")
    if not _take_slot(_client_ip(request), time.time()):
        raise HTTPException(status_code=429, detail="Sam has taken a lot of calls this hour. Try again later.",
                            headers={"Retry-After": "600"})
    try:
        token = dg.grant_token()
    except Exception:  # noqa: BLE001
        log.exception("Deepgram token grant failed")
        raise HTTPException(status_code=502, detail="Couldn't reach Deepgram. Try again in a minute.")
    conv, session = dg.new_session()
    return {"token": token, "url": dg.AGENT_URL, "settings": dg.settings(), "session": session,
            "call_ref": call_ref(conv), "max_call_seconds": dg.MAX_CALL_SECONDS}


class ToolCall(BaseModel):
    session: str = Field(..., max_length=200)
    name: str = Field(..., max_length=40)
    arguments: str = Field("{}", max_length=8000)  # the JSON string from Deepgram's FunctionCallRequest


@router.post("/api/deepgram/tool")
def run_tool(call: ToolCall) -> dict:
    conv = _session(call.session)
    if call.name not in TOOLS:
        return {"content": json.dumps({"error": f"There is no {call.name} tool on this line."})}
    _tool_calls[conv] += 1
    if _tool_calls[conv] > dg.MAX_TOOL_CALLS:
        return {"content": json.dumps({"error": "Too many tool calls on this call. Apologize and close the call."})}
    try:
        args = json.loads(call.arguments or "{}")
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
    except ValueError:
        return {"content": json.dumps({"error": "The arguments weren't valid JSON. Try the tool again."})}
    model, handler = TOOLS[call.name]
    if "conversation_id" in model.model_fields:
        args["conversation_id"] = conv  # always this call's, whatever the model sent
    try:
        req = model(**args)
    except Exception as e:  # noqa: BLE001 - pydantic's message tells the model what was missing
        return {"content": json.dumps({"error": f"Missing or invalid fields: {str(e)[:300]}"})}
    if call.name == "page_on_call_tech":
        # Only a ticket made on this call can page the technician
        ticket = get_store().get_ticket(req.ticket_id.strip().upper())
        if not ticket or ticket.get("conversation_id") != conv:
            return {"content": json.dumps({"paged": False, "message": "Only a ticket created on this call can be paged."})}
    try:
        result = handler(req)
    except Exception:  # noqa: BLE001
        log.exception("Deepgram tool %s failed", call.name)
        return {"content": json.dumps({"error": "The tool failed. Follow the guardrail for a failed tool."})}
    return {"content": json.dumps(result, default=str)}


class Turn(BaseModel):
    role: str = Field(..., max_length=20)
    content: str = Field("", max_length=2000)


class CallEnd(BaseModel):
    session: str = Field(..., max_length=200)
    transcript: list[Turn] = Field(default_factory=list, max_length=400)
    latencies: list[dict] = Field(default_factory=list, max_length=200)  # AgentStartedSpeaking messages
    duration_secs: float | None = Field(None, ge=0, le=3600)


@router.post("/api/deepgram/end")
def end_call(end: CallEnd) -> dict:
    conv = _session(end.session)
    if conv in _ended:
        return {"status": "already saved"}
    _ended.add(conv)
    text = dg.transcript_text([t.model_dump() for t in end.transcript])
    read = dg.read_transcript(text)
    # The same shape as evaluation.analyze, minus ElevenLabs' grades (Deepgram calls aren't graded by them)
    found = {
        "results": {}, "trace": [], "metrics": {"latency": dg.latency_summary(end.latencies)},
        "data": {"caller_sentiment": read["sentiment"]} if read.get("sentiment") else {},
        "summary": read.get("summary"), "call_successful": None,
        "duration_secs": round(end.duration_secs) if end.duration_secs is not None else None,
        "agent_id": dg.AGENT_ID, "transcript": evaluation.redact(text),
    }
    get_store().merge_call(conv, evaluation.record_fields(found))
    try:
        zendesk.sync_call(conv, found["summary"], found)
    except Exception:  # noqa: BLE001
        log.exception("Zendesk sync failed for %s", conv)
    return {"status": "ok"}
