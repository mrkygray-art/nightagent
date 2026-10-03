"""Back up NightAgent's ElevenLabs setup (agents, tools, QA tests) into elevenlabs/ as JSON.

Run:  ELEVENLABS_API_KEY=... python scripts/export_elevenlabs.py
A read-only key (ElevenAgents: Read) is enough. Secrets are never written: tool request
headers (which carry the tool secret) and anything named like a secret are replaced with
"<REDACTED>", and account details (creator email, permissions) are dropped.
"""
import json
import os
import re
import sys
from pathlib import Path

import requests

API = "https://api.elevenlabs.io/v1/convai"
OUT = Path(__file__).resolve().parent.parent / "elevenlabs"
AGENTS = {
    "sam": "agent_0301m3ws1zwae8ya6j72bcv7a193",
    "follow-up": "agent_5401m3x8ezgferwsyzb2rz1jdbc8",
    "jordan-billing": "agent_4001m3zfgp9efne9gm350187zpfb",
    "riley-sales": "agent_3001m3zg26pted8trz8p4pxt4qfc",
}
QA_FOLDER = "tfld_2901m3ztf2ybegfrkekye2d4b778"
DROP_KEYS = {"access_info", "access_permissions"}
SECRET_KEY = re.compile(r"secret|token|api[_-]?key|authorization|password", re.I)


def clean(value, key=""):
    """Copy of value with secrets redacted and account details dropped."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in DROP_KEYS:
                continue
            if k in ("headers", "request_headers") and isinstance(v, dict):
                out[k] = {h: "<REDACTED>" for h in v}
            elif SECRET_KEY.search(k) and isinstance(v, str) and v:
                out[k] = "<REDACTED>"
            else:
                out[k] = clean(v, k)
        return out
    if isinstance(value, list):
        return [clean(v, key) for v in value]
    if isinstance(value, str) and re.search(r"\bsk_[A-Za-z0-9]{20,}|p-[A-Za-z0-9_-]{30,}", value):
        return "<REDACTED>"
    return value


def get(session, path, **params):
    res = session.get(f"{API}{path}", params=params, timeout=20)
    res.raise_for_status()
    return res.json()


def save(name, data):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main():
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("Set ELEVENLABS_API_KEY (a read-only key is enough).")
    s = requests.Session()
    s.headers["xi-api-key"] = key

    tool_ids = set()
    for name, agent_id in AGENTS.items():
        agent = get(s, f"/agents/{agent_id}")
        save(f"agents/{name}.json", agent)
        prompt = agent.get("conversation_config", {}).get("agent", {}).get("prompt", {})
        tool_ids.update(prompt.get("tool_ids") or [])
        print("agent", name)

    for tool_id in sorted(tool_ids):
        tool = get(s, f"/tools/{tool_id}")
        tool_name = (tool.get("tool_config") or {}).get("name") or tool_id
        save(f"tools/{tool_name}.json", tool)
        print("tool", tool_name)

    listing = get(s, "/agent-testing", parent_folder_id=QA_FOLDER, page_size=100)
    tests = listing.get("tests") or listing.get("results") or []
    for item in tests:
        test = get(s, f"/agent-testing/{item['id']}")
        slug = re.sub(r"[^a-z0-9]+", "-", test.get("name", item["id"]).lower()).strip("-")[:60]
        save(f"tests/{slug}.json", test)
        print("test", slug)

    leaked = [p for p in OUT.rglob("*.json") if re.search(r"p-X6W|sk_[A-Za-z0-9]{20,}", p.read_text(encoding="utf-8"))]
    if leaked:
        sys.exit(f"Secret found in {leaked}; not safe to commit.")
    print(f"Saved to {OUT} ({len(AGENTS)} agents, {len(tool_ids)} tools, {len(tests)} tests); no secrets found.")


if __name__ == "__main__":
    main()
