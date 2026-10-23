"""Print a signed Deepgram call session and the agent Settings as JSON, for e2e/na-deepgram-test.js.
Run with the same TOOL_SECRET (or DEEPGRAM_SESSION_SECRET) as the local server."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import deepgram_voice as dg  # noqa: E402

_, session = dg.new_session()
print(json.dumps({"session": session, "settings": dg.settings()}))
