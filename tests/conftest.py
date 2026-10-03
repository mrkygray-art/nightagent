"""Tests run against the in-memory store, with no Supabase or ElevenLabs needed."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force the in-memory store and known secrets before the app is imported.
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""
os.environ["TOOL_SECRET"] = "test-tool-secret"
os.environ["ELEVENLABS_WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["ALLOW_UNSIGNED_WEBHOOKS"] = "false"
os.environ["ELEVENLABS_API_KEY"] = ""  # tests never call ElevenLabs
for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER", "ONCALL_TECH_PHONE"):
    os.environ[name] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.store import get_store  # noqa: E402
from main import app  # noqa: E402

TOOL_HEADERS = {"x-tool-secret": "test-tool-secret"}


@pytest.fixture(autouse=True)
def fresh_store():
    """Every test starts with a brand-new in-memory store."""
    config.TOOL_SECRET = "test-tool-secret"
    config.ELEVENLABS_WEBHOOK_SECRET = "test-webhook-secret"
    config.ALLOW_UNSIGNED_WEBHOOKS = False
    get_store.cache_clear()
    yield
    get_store.cache_clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tool(client):
    def call(path: str, body: dict):
        res = client.post(f"/tools/{path}", json=body, headers=TOOL_HEADERS)
        assert res.status_code == 200, res.text
        return res.json()
    return call
