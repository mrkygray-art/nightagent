"""All settings come from environment variables (or a local .env file)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes"}


TOOL_SECRET = os.getenv("TOOL_SECRET", "")
ELEVENLABS_WEBHOOK_SECRET = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "")
# Read-only key, server side only: reads each call's post-call analysis for the call check.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ALLOW_UNSIGNED_WEBHOOKS = _bool("ALLOW_UNSIGNED_WEBHOOKS")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
# Table name prefix, so the demo tables can live safely inside a shared Supabase project.
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "ns_")

# Public agent ID used by the /demo page (safe to expose; the agent is locked to allowed domains).
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "agent_0301m3ws1zwae8ya6j72bcv7a193")
# The follow-up agent (also public, also locked to the approved sites).
FOLLOWUP_AGENT_ID = os.getenv("FOLLOWUP_AGENT_ID", "agent_5401m3x8ezgferwsyzb2rz1jdbc8")
# Demo-wide cap on follow-up calls started per hour (each one uses ElevenLabs minutes).
FOLLOW_UPS_PER_HOUR = int(os.getenv("FOLLOW_UPS_PER_HOUR", "30"))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
ONCALL_TECH_PHONE = os.getenv("ONCALL_TECH_PHONE", "")
ONCALL_TECH_NAME = os.getenv("ONCALL_TECH_NAME", "the on-call technician")
CALLBACK_WINDOW_MINUTES = int(os.getenv("CALLBACK_WINDOW_MINUTES", "15"))
SMS_MAX_PER_HOUR = int(os.getenv("SMS_MAX_PER_HOUR", "5"))

# Zendesk: a ticket for each board ticket, made after the post-call webhook. Unset = off.
ZENDESK_SUBDOMAIN = os.getenv("ZENDESK_SUBDOMAIN", "")
ZENDESK_CLIENT_ID = os.getenv("ZENDESK_CLIENT_ID", "")
ZENDESK_CLIENT_SECRET = os.getenv("ZENDESK_CLIENT_SECRET", "")
# Ticket field ids (numbers from Admin Center > Objects and rules > Tickets > Fields). Unset = that field is left off.
ZENDESK_FIELD_NIGHTAGENT_ID = os.getenv("ZENDESK_FIELD_NIGHTAGENT_ID", "")
ZENDESK_FIELD_CATEGORY = os.getenv("ZENDESK_FIELD_CATEGORY", "")
ZENDESK_FIELD_CALL_SOURCE = os.getenv("ZENDESK_FIELD_CALL_SOURCE", "")
# Human review fields (made by scripts/zendesk_review_setup.py, which prints these ids). Unset = that field is left off;
# the needs_review tags and the note line go on either way.
ZENDESK_FIELD_REVIEW_NEEDED = os.getenv("ZENDESK_FIELD_REVIEW_NEEDED", "")
ZENDESK_FIELD_REVIEW_REASON = os.getenv("ZENDESK_FIELD_REVIEW_REASON", "")
ZENDESK_FIELD_RECOMMENDED_OPTIONS = os.getenv("ZENDESK_FIELD_RECOMMENDED_OPTIONS", "")
# Zendesk -> NightAgent status sync: the webhook's signing secret, and the Zendesk user id our own API calls run as
# (its changes are ignored, so nothing NightAgent does in Zendesk can loop back). Both unset = the endpoint is off.
ZENDESK_WEBHOOK_SECRET = os.getenv("ZENDESK_WEBHOOK_SECRET", "")
ZENDESK_INTEGRATION_USER_ID = os.getenv("ZENDESK_INTEGRATION_USER_ID", "")

# The "NightAgent Call" Zendesk sidebar app sends this in X-Sidebar-Secret. Unset = the endpoint is off.
SIDEBAR_SECRET = os.getenv("SIDEBAR_SECRET", "")
SIDEBAR_REQUESTS_PER_MINUTE = int(os.getenv("SIDEBAR_REQUESTS_PER_MINUTE", "60"))

# Sam on Deepgram (app/deepgram_voice.py). Unset key = the /deepgram page says it isn't set up.
# The key needs Member permissions (it grants the browser's short-lived tokens) and stays server side.
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_SESSION_SECRET = os.getenv("DEEPGRAM_SESSION_SECRET", "")  # signs call sessions; falls back to TOOL_SECRET
DEEPGRAM_LLM = os.getenv("DEEPGRAM_LLM", "claude-haiku-4-5")  # Deepgram-managed Anthropic model
DEEPGRAM_VOICE = os.getenv("DEEPGRAM_VOICE", "aura-2-thalia-en")
DEEPGRAM_CALLS_PER_HOUR = int(os.getenv("DEEPGRAM_CALLS_PER_HOUR", "20"))  # per server instance, all callers
DEEPGRAM_CALLS_PER_IP_HOUR = int(os.getenv("DEEPGRAM_CALLS_PER_IP_HOUR", "5"))
