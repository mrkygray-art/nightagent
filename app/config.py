"""All settings come from environment variables (or a local .env file)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes"}


TOOL_SECRET = os.getenv("TOOL_SECRET", "")
ELEVENLABS_WEBHOOK_SECRET = os.getenv("ELEVENLABS_WEBHOOK_SECRET", "")
ALLOW_UNSIGNED_WEBHOOKS = _bool("ALLOW_UNSIGNED_WEBHOOKS")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
# Table name prefix, so the demo tables can live safely inside a shared Supabase project.
TABLE_PREFIX = os.getenv("TABLE_PREFIX", "ns_")

# Public agent ID used by the /demo page (safe to expose; the agent is locked to allowed domains).
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "agent_0301m3ws1zwae8ya6j72bcv7a193")
# The follow-up agent (also public, also locked to the approved sites).
FOLLOWUP_AGENT_ID = os.getenv("FOLLOWUP_AGENT_ID", "")
# Demo-wide cap on follow-up calls started per hour (each one uses ElevenLabs minutes).
FOLLOW_UPS_PER_HOUR = int(os.getenv("FOLLOW_UPS_PER_HOUR", "30"))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
ONCALL_TECH_PHONE = os.getenv("ONCALL_TECH_PHONE", "")
ONCALL_TECH_NAME = os.getenv("ONCALL_TECH_NAME", "the on-call technician")
CALLBACK_WINDOW_MINUTES = int(os.getenv("CALLBACK_WINDOW_MINUTES", "15"))
SMS_MAX_PER_HOUR = int(os.getenv("SMS_MAX_PER_HOUR", "5"))
