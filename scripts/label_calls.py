"""Score real calls yourself, so the Evaluation Lab can show how often the AI judge agrees with a person.

For each graded call you haven't labeled yet, this shows the (redacted) transcript, then asks your verdict
on each AI-judged check BEFORE showing the AI's verdict, so you aren't anchored by it. Answers go to
app/judge_labels.json, keyed by call_ref, never by conversation id.

Needs SUPABASE_URL and SUPABASE_SERVICE_KEY (to read the calls) and, for calls without a stored
transcript, ELEVENLABS_API_KEY (the transcript is fetched, shown, and not saved).

    .venv/Scripts/python scripts/label_calls.py            # label up to 10 calls
    .venv/Scripts/python scripts/label_calls.py --limit 30
    .venv/Scripts/python scripts/label_calls.py --forget 1a2b3c4d   # drop your verdicts on one call, to redo it

Only the checks the AI graded on a call are asked (older calls have 2; front-desk calls from 2026-10-07 on
have 8; check-in calls have their own 4), so every verdict can be compared.

Keys: s = success, f = failure, u = doesn't apply, Enter = skip this check, q = save and quit.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests  # noqa: E402

from app import config, judge, voice_lab  # noqa: E402
from app.analysis_spec import CRITERIA, FOLLOW_UP_CRITERIA  # noqa: E402
from app.evaluation import redact, transcript_text  # noqa: E402
from app.service import call_ref  # noqa: E402
from app.store import get_store  # noqa: E402

ANSWERS = {"s": "success", "f": "failure", "u": "unknown"}


def transcript(cid: str, row: dict) -> str:
    if row.get("transcript"):
        return row["transcript"]
    if not config.ELEVENLABS_API_KEY:
        return "(No stored transcript, and no ELEVENLABS_API_KEY to fetch it.)"
    res = requests.get(f"https://api.elevenlabs.io/v1/convai/conversations/{cid}",
                       headers={"xi-api-key": config.ELEVENLABS_API_KEY}, timeout=15)
    res.raise_for_status()
    return redact(transcript_text(res.json().get("transcript"))) or "(Empty transcript.)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--forget", metavar="CALL_REF", help="remove your verdicts on one call (the id shown in its header)")
    args = parser.parse_args()

    if args.forget:
        kept = [lab for lab in judge.labels() if not lab["call_ref"].startswith(args.forget)]
        removed = len(judge.labels()) - len(kept)
        judge.LABELS.write_text(json.dumps({"labels": kept}, indent=2) + "\n", encoding="utf-8")
        print(f"Removed {removed} verdicts. Run without --forget to score that call again.")
        return

    store = get_store()
    if store.name != "supabase":
        sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first: there are no real calls in the in-memory store.")
    saved = judge.labels()
    done = {(lab["call_ref"], lab["criterion"]) for lab in saved}
    ids = list(dict.fromkeys(r["conversation_id"] for r in store.recent_tool_calls(2000)
                             if r.get("conversation_id") and not voice_lab.is_test(r["conversation_id"])))
    calls = store.calls_by_ids(ids)
    def graded(cid):  # the checks the AI actually graded on this call, in rubric order
        results = ((calls.get(cid) or {}).get("evaluation") or {}).get("results") or {}
        return [c for c in CRITERIA + FOLLOW_UP_CRITERIA if c["id"] in results]

    todo = [cid for cid in ids if (calls.get(cid) or {}).get("eval_status") == "done"
            and any((call_ref(cid), c["id"]) not in done for c in graded(cid))][:args.limit]
    print(f"{len(todo)} calls to label. s = success, f = failure, u = doesn't apply, Enter = skip, q = quit.\n")

    new = []
    try:
        for i, cid in enumerate(todo, 1):
            ref = call_ref(cid)
            print(f"=== Call {i} of {len(todo)} ({ref}) ===\n{transcript(cid, calls[cid])}\n")
            results = (calls[cid].get("evaluation") or {}).get("results") or {}
            for c in graded(cid):
                if (ref, c["id"]) in done:
                    continue
                print(f"-- {c['name']}\n   {c['conversation_goal_prompt']}")
                answer = input("   Your verdict [s/f/u, Enter skip, q quit]: ").strip().lower()
                if answer == "q":
                    raise KeyboardInterrupt
                if answer not in ANSWERS:
                    continue
                note = input("   Note (optional): ").strip()
                ai = (results.get(c["id"]) or {}).get("result") or "not graded"
                print(f"   AI said: {ai}" + ("  (agrees)" if ai == ANSWERS[answer] else "  (DIFFERENT)") + "\n")
                new.append({"call_ref": ref, "criterion": c["id"], "human": ANSWERS[answer], "note": note,
                            "labeled_at": datetime.now(timezone.utc).date().isoformat()})
    except (KeyboardInterrupt, EOFError):
        print("\nStopping.")
    if new:
        judge.LABELS.write_text(json.dumps({"labels": saved + new}, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(new)} new labels ({len(saved) + len(new)} in all) to {judge.LABELS}.")


if __name__ == "__main__":
    main()
