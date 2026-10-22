"""Post-call webhook: ElevenLabs sends the transcript and analysis after each call ends.

Attach it to each agent in ElevenLabs (Agent > Advanced > Post-call webhook), pointed at
/webhooks/elevenlabs/post-call, with its signing secret in ELEVENLABS_WEBHOOK_SECRET."""
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app import config, evaluation, zendesk, zendesk_sync
from app.security import verify_elevenlabs_signature
from app.store import get_store

router = APIRouter(prefix="/webhooks")
log = logging.getLogger("nightshift")


@router.post("/elevenlabs/post-call")
async def post_call(request: Request) -> dict:
    raw = await request.body()  # verify against the exact raw bytes, before parsing
    signature = request.headers.get("elevenlabs-signature")

    if not config.ALLOW_UNSIGNED_WEBHOOKS and not verify_elevenlabs_signature(
        raw, signature, config.ELEVENLABS_WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Body is not valid JSON")

    if event.get("type") != "post_call_transcription":
        return {"status": "ignored", "type": event.get("type")}  # still 200 so it isn't retried

    data = event.get("data") or {}
    conversation_id = data.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="Missing conversation_id")

    # Same parsing as the on-demand fetch (app/evaluation.py): grades, data collection, metrics, the
    # call length, and the transcript with phone numbers cut to the last four digits.
    found = evaluation.analyze(data)
    get_store().merge_call(conversation_id, evaluation.record_fields(found))
    log.info("Stored post-call data for %s", conversation_id)
    try:  # after the call is stored, and never able to undo that
        zendesk.sync_call(conversation_id, found["summary"], found)
    except Exception:  # noqa: BLE001
        log.exception("Zendesk sync failed for %s", conversation_id)
    return {"status": "ok"}


MAX_ZENDESK_BODY = 16_000  # the trigger's body is a few hundred bytes


@router.post("/zendesk/ticket-updated")
async def zendesk_ticket_updated(request: Request):
    """Zendesk trigger webhook: a nightagent-tagged ticket changed status or assignee (see app/zendesk_sync.py).
    The signature is checked before anything is read or written. The work after it is a few store writes, done
    before answering (work left for after the response can be cut off when a serverless function freezes);
    it is well inside Zendesk's 12-second timeout. Every handled delivery gets a 200, even one that's ignored,
    so Zendesk doesn't retry it. Only a store failure answers 503 with Retry-After, which Zendesk retries,
    and a retry is safe because repeats are ignored."""
    if not zendesk_sync.configured():
        raise HTTPException(status_code=503, detail="Zendesk sync is not configured")
    raw = await request.body()
    if len(raw) > MAX_ZENDESK_BODY:
        raise HTTPException(status_code=413, detail="Body too large")
    if not zendesk_sync.verify(raw, request.headers.get(zendesk_sync.SIGNATURE_HEADER),
                               request.headers.get(zendesk_sync.TIMESTAMP_HEADER), config.ZENDESK_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Body is not valid JSON")
    # Logged to trace a delivery. Not the duplicate key: Zendesk documents the header but not that a retry keeps
    # it, and one change can fire the webhook twice; repeats are caught by updated_at in apply_update.
    invocation = (request.headers.get(zendesk_sync.INVOCATION_HEADER) or "")[:80]
    try:
        outcome = zendesk_sync.apply_update(payload)
    except Exception:  # noqa: BLE001 - a store failure: let Zendesk try again shortly
        log.exception("Zendesk sync: could not apply invocation %s", invocation)
        return JSONResponse({"status": "retry"}, status_code=503, headers={"Retry-After": "30"})
    log.info("Zendesk sync invocation %s: %s (%s)", invocation, outcome["result"],
             outcome.get("reason") or outcome.get("board_status"))
    return {"status": "ok", **outcome}
