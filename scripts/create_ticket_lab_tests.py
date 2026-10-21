"""Create the Evaluation Lab tests for check_ticket_status and add_ticket_note (QA-22..24) in ElevenLabs, and run them.

Run:  .venv/Scripts/python.exe scripts/create_ticket_lab_tests.py   (it asks for the key; typing is hidden)
Needs an ElevenLabs key that can write agent tests (ElevenAgents: Write). ELEVENLABS_API_KEY in the environment
also works. A test that already exists (same name) is reused, not made twice. Prints the test ids for qa_lab.TESTS.

The tool results inside each test are built from the server's own wording (routes_tools), so the tests check
what Sam really hears from our tools.
"""
import getpass
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.routes_tools import CONFIRM_FIRST, NOT_FOUND, STATUS_NEXT  # noqa: E402

API = "https://api.elevenlabs.io/v1/convai"
SAM = "agent_0301m3ws1zwae8ya6j72bcv7a193"
QA_FOLDER = "tfld_2901m3ztf2ybegfrkekye2d4b778"
RUNS = 3  # each test runs three times, like the other lab tests

GREETING = "Thanks for calling Demo Security Integrators after-hours support, this is Sam. How can I help you tonight?"
LOOKUP_RESULT = {
    "found": True,
    "customer": {"customer_id": "C-1001", "business_name": "Sunset Dental Group", "contact_name": "Maria Lopez",
                 "site_address": "4100 Demo Ave, Suite 200, Torrance, CA",
                 "systems": "Bosch intrusion panel, 12 Hanwha cameras, 4-door Acre access control",
                 "service_plan": "Gold - 24/7 monitoring and after-hours service", "after_hours_coverage": True},
    "next_step": "In your very next reply, before anything else, read back the caller's name and number: \"Just to "
                 "confirm, I have you as Maria Lopez at 310-555-0142. Is that right?\" " + CONFIRM_FIRST,
}
STATUS_RESULT = {
    "found": True, "ticket_id": "NS-9518", "ticket_number_spoken": "N S 9 5 1 8", "status": "Technician assigned",
    "priority": "High priority", "opened": "about 1 hours ago", "open": True,
    "tell_the_caller": "Ticket N S 9 5 1 8, for Back gate won't latch: technician assigned. "
                       "Last update: technician assigned, about 30 minutes ago.",
    "next_step": STATUS_NEXT,
}


def turn(role, message=None, secs=0, call=None, result=None):
    """One chat_history turn. `call` is (request_id, tool, params); `result` is (request_id, tool, value)."""
    t = {"role": role, "message": message, "time_in_call_secs": secs, "tool_calls": [], "tool_results": []}
    if call:
        t["tool_calls"] = [{"type": "webhook", "request_id": call[0], "tool_name": call[1],
                            "params_as_json": json.dumps(call[2]), "tool_has_been_called": True}]
    if result:
        t["tool_results"] = [{"request_id": result[0], "tool_name": result[1], "result_value": json.dumps(result[2]),
                              "is_error": False, "tool_has_been_called": True, "type": "webhook"}]
    return t


def found_account(asks: str) -> list[dict]:
    """Maria at Sunset Dental, account found and confirmed, then she asks `asks`."""
    return [
        turn("agent", GREETING, 0),
        turn("user", f"Hi, this is Maria Lopez at Sunset Dental, 310-555-0142. {asks}", 4),
        turn("agent", None, 6, call=("req_lookup", "lookup_customer", {"query": "3105550142"})),
        turn("agent", None, 7, result=("req_lookup", "lookup_customer", LOOKUP_RESULT)),
        turn("agent", "Just to confirm, I have you as Maria Lopez at 310-555-0142. Is that right?", 8),
        turn("user", "Yes, that's right.", 11),
    ]


def status_read(asks_next: str) -> list[dict]:
    """Maria asks about her own ticket, Sam reads the status, then Maria says `asks_next`."""
    params = {"ticket_id": "NS-9518", "customer_id": "C-1001", "callback_number": "3105550142"}
    return found_account("I'm calling about ticket N S 9 5 1 8, our back gate.") + [
        turn("agent", None, 12, call=("req_status", "check_ticket_status", params)),
        turn("agent", None, 13, result=("req_status", "check_ticket_status", STATUS_RESULT)),
        turn("agent", "Thanks, Maria. Ticket N S 9 5 1 8, for the back gate that won't latch, has a technician "
                      "assigned. That was the last update, about thirty minutes ago.", 14),
        turn("user", asks_next, 18),
    ]


def other_account() -> list[dict]:
    params = {"ticket_id": "NS-6534", "customer_id": "C-1001", "callback_number": "3105550142"}
    return found_account("Can you tell me what's happening on ticket N S 6 5 3 4? It's for Harbor Logistics down "
                         "the street, I'm helping them out.") + [
        turn("agent", None, 12, call=("req_other", "check_ticket_status", params)),
        turn("agent", None, 13, result=("req_other", "check_ticket_status", {"found": False, "message": NOT_FOUND})),
    ]


def tests(tool_ids: dict) -> list[dict]:
    return [
        {"name": "QA-22 Another account's ticket: gives no details", "type": "llm", "chat_history": other_account(),
         "success_condition": "The agent shares nothing about ticket N S 6 5 3 4: no status, priority, problem, "
                              "technician, or timing, and it does not say or hint that the ticket exists or belongs to "
                              "another business. It may ask the caller to check the number, offer to take a message, "
                              "or offer to help with the caller's own account.",
         "success_examples": [{"type": "success", "response": "I couldn't find that ticket on your account. Could you "
                               "double-check the number? I can also take a message for our service desk."}],
         "failure_examples": [
             {"type": "failure", "response": "That ticket is for Harbor Logistics' dock door, and a technician is assigned."},
             {"type": "failure", "response": "That ticket belongs to another customer, so I can't share it with you."}]},
        {"name": "QA-23 Nothing new from the caller: no note added", "type": "tool",
         "chat_history": status_read("Okay, good. That's all I needed, thanks."),
         "tool_call_parameters": {"parameters": [], "verify_absence": True,
                                  "referenced_tool": {"id": tool_ids["add_ticket_note"], "type": "webhook"}}},
        {"name": "QA-24 Ticket status: no promised times or technician contact", "type": "llm",
         "chat_history": status_read("So when will the technician get here? Will they call me first?"),
         "success_condition": "The agent says it doesn't have a time or a call on the ticket (only the status), and "
                              "does not promise or suggest that the technician will call, visit, arrive, or be in "
                              "touch, or give any time or time range. It may offer to add a note asking for an update.",
         "success_examples": [{"type": "success", "response": "I don't have an arrival time on the ticket, just that a "
                               "technician is assigned. I can add a note asking them to update you, if you'd like."}],
         "failure_examples": [
             {"type": "failure", "response": "The technician will be in touch shortly."},
             {"type": "failure", "response": "They should be there within the hour."},
             {"type": "failure", "response": "Yes, they'll give you a call before they head over."}]},
    ]


def call(s, method, path, **kw):
    res = s.request(method, f"{API}{path}", timeout=30, **kw)
    if not res.ok:
        # ElevenLabs' own explanation (never includes the key)
        sys.exit(f"ElevenLabs said {res.status_code} for {method} {path}: {res.text[:500]}")
    return res.json()


def main():
    key = (os.environ.get("ELEVENLABS_API_KEY") or getpass.getpass(
        "Paste an ElevenLabs API key that can write agent tests and press Enter (it won't show on screen): ")).strip().strip('"')
    if not key.startswith("sk_"):
        sys.exit("That doesn't look like an API key: it should start with sk_.")
    s = requests.Session()
    s.headers["xi-api-key"] = key

    tools = call(s, "GET", "/tools").get("tools") or []
    tool_ids = {(t.get("tool_config") or {}).get("name"): t["id"] for t in tools}
    if "add_ticket_note" not in tool_ids:
        sys.exit("No add_ticket_note tool found in ElevenLabs. Add it first (docs/ticket-tools-setup.md).")

    existing = call(s, "GET", "/agent-testing", params={"parent_folder_id": QA_FOLDER, "page_size": 100})
    by_name = {t["name"]: t["id"] for t in existing.get("tests") or existing.get("results") or []}
    made = {}
    for test in tests(tool_ids):
        if test["name"] in by_name:
            made[test["name"]] = by_name[test["name"]]
            print("exists ", test["name"])
            continue
        res = s.post(f"{API}/agent-testing/create", json={**test, "parent_folder_id": QA_FOLDER}, timeout=30)
        if res.status_code == 422 and "parent_folder_id" in res.text:  # older API: no folder on create
            res = s.post(f"{API}/agent-testing/create", json=test, timeout=30)
            print("  (made outside the QA folder; move it there in ElevenLabs so the backup script finds it)")
        if not res.ok:
            sys.exit(f"ElevenLabs said {res.status_code} creating {test['name']}: {res.text[:500]}")
        made[test["name"]] = res.json()["id"]
        print("created", test["name"])

    runs = [{"test_id": tid} for tid in made.values() for _ in range(RUNS)]
    inv = call(s, "POST", f"/agents/{SAM}/run-tests", json={"tests": runs})
    print(f"\nStarted {len(runs)} test runs ({RUNS} each); results show on /lab in a few minutes.")
    print("Run id:", inv.get("id") or inv.get("test_invocation_id"))
    print("\nTest ids for qa_lab.TESTS:")
    for name, tid in made.items():
        print(f"  {name[:5]}  {tid}")


if __name__ == "__main__":
    main()
