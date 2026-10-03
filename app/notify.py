"""SMS paging through Twilio, with a simple rate limit so a public demo can't spam your phone.

If Twilio isn't configured, pages are simulated and written to the log instead.
Note: the rate limit lives in memory, so on serverless hosting it is per-instance (good
enough for a demo; use a database counter for production).
"""
import logging
import time
from collections import deque

from app import config

log = logging.getLogger("nightshift")
_sent_at: deque[float] = deque()


def _twilio_configured() -> bool:
    return all(
        [config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN,
         config.TWILIO_FROM_NUMBER, config.ONCALL_TECH_PHONE]
    )


def _under_rate_limit() -> bool:
    cutoff = time.time() - 3600
    while _sent_at and _sent_at[0] < cutoff:
        _sent_at.popleft()
    return len(_sent_at) < config.SMS_MAX_PER_HOUR


def page_on_call(body: str) -> dict:
    from app.store import in_sandbox
    if in_sandbox() or not _twilio_configured():
        log.info("SIMULATED PAGE: %s", body)
        return {"sent": False, "simulated": True}

    if not _under_rate_limit():
        log.warning("Page suppressed by rate limit: %s", body)
        return {"sent": False, "simulated": True, "rate_limited": True}

    from twilio.rest import Client

    client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        to=config.ONCALL_TECH_PHONE, from_=config.TWILIO_FROM_NUMBER, body=body[:320]
    )
    _sent_at.append(time.time())
    return {"sent": True, "simulated": False, "sid": message.sid}
