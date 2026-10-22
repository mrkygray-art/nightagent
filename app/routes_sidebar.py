"""The "NightAgent Call" Zendesk sidebar app's backend: one read-only endpoint.

GET /api/zendesk/tickets/{zendesk_ticket_id} with the SIDEBAR_SECRET in X-Sidebar-Secret. Off (503) until
SIDEBAR_SECRET is set. 404 for any Zendesk ticket NightAgent didn't make, so it can't be used to probe Zendesk.
The rate limit runs before the secret check, so guesses count too. It lives in memory, so on serverless
hosting it is per instance (like the SMS limit in app/notify.py). Requests proxied by Zendesk all come from
Zendesk's servers, so in practice the limit is shared by everyone using the app.
"""
import hmac
import logging
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Header, HTTPException, Path, Request, Response

from app import config, sidebar
from app.store import get_store

router = APIRouter(prefix="/api/zendesk")
log = logging.getLogger("nightshift")

WINDOW_SECS = 60
_hits: dict[str, deque] = defaultdict(deque)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")  # set by Vercel
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _rate_limit(request: Request) -> None:
    now, hits = time.time(), _hits[_client_key(request)]
    while hits and hits[0] <= now - WINDOW_SECS:
        hits.popleft()
    if len(hits) >= config.SIDEBAR_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Too many requests", headers={"Retry-After": str(WINDOW_SECS)})
    hits.append(now)


def _require_secret(given: str | None) -> None:
    if not config.SIDEBAR_SECRET:
        log.warning("SIDEBAR_SECRET is not set; the Zendesk sidebar endpoint is off.")
        raise HTTPException(status_code=503, detail="Sidebar is not set up")
    if not given or not hmac.compare_digest(given.encode(), config.SIDEBAR_SECRET.encode()):
        raise HTTPException(status_code=401, detail="Invalid sidebar secret")


@router.get("/tickets/{zendesk_ticket_id}")
def zendesk_ticket(request: Request, response: Response,
                   zendesk_ticket_id: int = Path(ge=1, le=2**53),
                   x_sidebar_secret: str | None = Header(default=None)) -> dict:
    _rate_limit(request)
    _require_secret(x_sidebar_secret)
    response.headers["Cache-Control"] = "no-store"
    store = get_store()
    ticket = store.ticket_by_zendesk_id(zendesk_ticket_id)
    if not ticket or ticket.get("scenario"):
        raise HTTPException(status_code=404, detail="Not a NightAgent ticket")
    conv = ticket.get("conversation_id")
    call = store.calls_by_ids([conv]).get(conv) if conv else None
    logged = [r for r in store.tool_calls_for(ticket["ticket_id"], [conv] if conv else [])
              if not conv or r.get("conversation_id") in (conv, None)]
    return sidebar.build(ticket, zendesk_ticket_id, call, logged)
