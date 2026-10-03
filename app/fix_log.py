"""Evaluation Lab fixes log: real problems, why they happened, what changed, and how they test now.

Written by hand, and only from things that really happened: each entry points at the commit or the
agent prompt that changed, and at the tests that guard it. "Before" is what was recorded when the
problem was found. "Now" is read live from the latest test runs, so a fix that stops holding shows it.
"""
from __future__ import annotations

from app import qa_lab

# A short fixed list, so causes can be counted later
CAUSES = {
    "intent": "Read the situation wrong",
    "instructions": "Didn't follow its steps",
    "made_up": "Filled in details nobody said",
    "persona": "Spoke the wrong way",
    "server": "Missing safety net in our server",
}

QA = {f"QA-{meta['name'][3:5]}": tid for tid, meta in qa_lab.TESTS.items()}

FIXES = [
    {"id": "FIX-01", "title": "A gate stuck open was treated as medium priority",
     "found": "Live call", "cause": "intent",
     "why": "Sam didn't see a gate that won't close as a site that can't be secured.",
     "fix": "Sam's list of problem types now names a gate that sticks open as an emergency. Our rules still set the final priority.",
     "where": "Sam's prompt (ElevenLabs)", "before": "Suggested medium in a live call", "tests": ["QA-03"]},
    {"id": "FIX-02", "title": "The after-hours billing sentence was left out, or said when it shouldn't be",
     "found": "Live calls", "cause": "instructions",
     "why": "Sam was deciding from the customer's plan whether to mention the extra charge, and got it wrong both ways.",
     "fix": "The server now decides, and hands Sam the exact sentence to say (or none).",
     "where": "Commits e8d6117, b4fb77c", "before": "Wrong in live calls, both ways", "tests": ["QA-04", "QA-05"]},
    {"id": "FIX-03", "title": "Tickets were opened before the caller confirmed their name and number",
     "found": "Live calls", "cause": "instructions",
     "why": "The rule was in Sam's prompt, but the prompt alone wasn't enough for this model.",
     "fix": "The account lookup's answer now tells Sam to read the name and number back before any ticket.",
     "where": "Commit 1aeff85", "before": "Skipped in live calls",
     "proof": "Checked on live calls NS-1504, NS-5975, NS-8906", "tests": ["QA-02"]},
    {"id": "FIX-04", "title": "Jordan talked about itself in the third person",
     "found": "Live call", "cause": "persona",
     "why": "After a handoff, Jordan said things like \"Jordan will look into it\".",
     "fix": "Jordan's first line is now written in the first person, and it never refers to itself by name.",
     "where": "Jordan's prompt (ElevenLabs)", "before": "Third person in a live call", "tests": ["QA-08"]},
    {"id": "FIX-05", "title": "Riley filled in \"not specified\" for things the caller never said",
     "found": "Live call", "cause": "made_up",
     "why": "The model filled empty fields with placeholder words instead of leaving them blank.",
     "fix": "The server treats placeholder answers (not specified, N/A, none) as blank.",
     "where": "Commit 0a5d358", "before": "Placeholders saved on a sales lead", "tests": ["QA-12"]},
    {"id": "FIX-06", "title": "A complaint hid a repair that was still needed",
     "found": "Live call", "cause": "intent",
     "why": "A caller asked for a supervisor about a gate that still wouldn't close; only a message was taken.",
     "fix": "If something is still broken, Sam opens a repair ticket first and attaches the complaint to it.",
     "where": "Commit 67d7461", "before": "Message only, no repair ticket", "tests": ["QA-07"]},
    {"id": "FIX-07", "title": "The read-back was still skipped when callers gave everything up front",
     "found": "Live call, after FIX-03", "cause": "instructions",
     "why": "When the caller said their name, number, and problem in one go, Sam went straight to the problem.",
     "fix": "The lookup's answer now gives Sam the exact sentence to say in its very next reply.",
     "where": "Commit 51b83e2", "before": "Skipped in a live call", "proof": "NS-2431 then scored 100% on the call check",
     "tests": ["QA-01"]},
    {"id": "FIX-08", "title": "A second report of the same problem opened a duplicate ticket and alerted again",
     "found": "Failure injection", "cause": "server",
     "why": "Nothing checked for an open ticket at the same site before opening a new one.",
     "fix": "The server joins a repeat report to the open ticket and tells Sam the technician already has it.",
     "where": "Commit 13be97c", "before": "Duplicate ticket and a second alert", "tests": ["QA-09", "QA-10"],
     "scenario": "Same caller twice"},
    {"id": "FIX-09", "title": "If the alert service failed, the technician was never told",
     "found": "Failure injection", "cause": "server",
     "why": "A failed alert wasn't recorded or retried.",
     "fix": "A failed alert is logged on the ticket and Sam retries once. If it fails again, Sam tells the caller "
            "the ticket is saved and flagged, without promising a callback time.",
     "where": "Commit 26e9be1", "before": "Failed silently", "tests": [], "scenario": "Alert service down"},
    {"id": "FIX-10", "title": "A burning smell from the panel didn't always get \"call 911\"",
     "found": "New test (QA-14)", "cause": "intent",
     "why": "Sam's 911 rule listed fire and smoke, but not a burning smell, sparks, or a hot panel.",
     "fix": "Those now trigger 911 right away, said as a plain instruction before anything else.",
     "where": "Sam's prompt (ElevenLabs), commit 05b3ee2", "before": "2 of 3 test runs passed", "tests": ["QA-14"]},
    {"id": "FIX-11", "title": "A caller who wouldn't give a name was refused help",
     "found": "New test (QA-15)", "cause": "instructions",
     "why": "Sam's steps asked for a full name every time, so it insisted a name was required.",
     "fix": "Sam can skip the name: it confirms the callback number only and never makes a name up. The server saves the name as blank.",
     "where": "Sam's prompt (ElevenLabs), commit 05b3ee2", "before": "0 of 3 test runs passed", "tests": ["QA-15"]},
]


def fixes(lab: dict) -> list[dict]:
    """Newest first, each with its live "now" result from the latest test runs."""
    by_id = {t["test_id"]: t for t in lab.get("tests") or []}
    out = []
    for f in reversed(FIXES):
        rows = [by_id.get(QA[q]) or {} for q in f["tests"]]
        passed = sum(r.get("passed", 0) for r in rows)
        done = passed + sum(r.get("failed", 0) for r in rows)
        out.append({**f, "cause_label": CAUSES[f["cause"]],
                    "now": {"passed": passed, "finished": done, "holding": done > 0 and passed == done}})
    return out
