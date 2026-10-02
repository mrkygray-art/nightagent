"""Post-call webhook: ElevenLabs sends the transcript and analysis after each call ends."""
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app import config
from app.security import verify_elevenlabs_signature
from app.store import get_store

router = APIRouter(prefix="/webhooks")
log = logging.getLogger("nightshift")


def _transcript_text(turns: list[dict] | None) -> str:
    lines = []
    for turn in turns or []:
        message = (turn.get("message") or "").strip()
        if not message:
            continue  # tool-call turns can have an empty message
        speaker = "Agent" if turn.get("role") == "agent" else "Caller"
        lines.append(f"{speaker}: {message}")
    return "\n".join(lines)


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

    analysis = data.get("analysis") or {}
    metadata = data.get("metadata") or {}
    get_store().upsert_call({
        "conversation_id": conversation_id,
        "agent_id": data.get("agent_id"),
        "summary": analysis.get("transcript_summary"),
        "call_successful": analysis.get("call_successful"),
        "duration_secs": metadata.get("call_duration_secs"),
        "transcript": _transcript_text(data.get("transcript")),
    })
    log.info("Stored post-call data for %s", conversation_id)
    return {"status": "ok"}
