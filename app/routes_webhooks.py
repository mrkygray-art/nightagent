"""Post-call webhook: ElevenLabs sends the transcript and analysis after each call ends.

Attach it to each agent in ElevenLabs (Agent > Advanced > Post-call webhook), pointed at
/webhooks/elevenlabs/post-call, with its signing secret in ELEVENLABS_WEBHOOK_SECRET."""
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app import config, evaluation
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
    get_store().merge_call(conversation_id, evaluation.record_fields(evaluation.analyze(data)))
    log.info("Stored post-call data for %s", conversation_id)
    return {"status": "ok"}
