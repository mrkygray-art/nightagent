"""Request authentication for both directions of the ElevenLabs integration."""
import hashlib
import hmac
import logging
import time

from fastapi import Header, HTTPException

from app import config

log = logging.getLogger("nightshift")

SIGNATURE_TOLERANCE_SECONDS = 30 * 60


def require_tool_secret(x_tool_secret: str | None = Header(default=None)) -> None:
    """Server tools: the agent sends a shared secret header we set at tool creation."""
    if not config.TOOL_SECRET:
        log.warning("TOOL_SECRET is not set; tool endpoints are unprotected (local dev only).")
        return
    if not x_tool_secret or not hmac.compare_digest(x_tool_secret, config.TOOL_SECRET):
        raise HTTPException(status_code=401, detail="Invalid tool secret")


def verify_elevenlabs_signature(
    raw_body: bytes,
    signature_header: str | None,
    secret: str,
    now: int | None = None,
    tolerance: int = SIGNATURE_TOLERANCE_SECONDS,
) -> bool:
    """Verify the ElevenLabs-Signature header on post-call webhooks.

    Header format: t=<unix timestamp>,v0=<hex HMAC-SHA256 of "<timestamp>.<raw body>">
    The header can carry more than one v0 signature (during secret rotation).
    """
    if not signature_header or not secret:
        return False

    timestamp = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            timestamp = value
        elif key == "v0":
            signatures.append(value)

    if timestamp is None or not signatures:
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False

    current = int(time.time()) if now is None else now
    if abs(current - ts) > tolerance:
        return False  # too old (or from the future): reject replays

    expected = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)
