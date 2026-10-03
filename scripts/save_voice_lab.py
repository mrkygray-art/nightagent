"""Save a voice-test run (voicelab/out/run-*.json) as app/voice_lab.json, which the /lab page reads.

    .venv/Scripts/python scripts/save_voice_lab.py voicelab/out/run-123.json [--other conv_a,conv_b]

--other lists conversation ids from trial calls that aren't part of the saved run; they're kept only so
the server leaves them out of the real-call numbers too.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

parser = argparse.ArgumentParser()
parser.add_argument("run")
parser.add_argument("--other", default="")
args = parser.parse_args()

run = json.loads(Path(args.run).read_text(encoding="utf-8"))
sources = json.loads((ROOT / "voicelab" / "clips" / "sources.json").read_text(encoding="utf-8"))
target = ROOT / "app" / "voice_lab.json"
previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}

other = set(previous.get("other_test_conversations") or [])
other |= {r.get("conversation_id") for r in previous.get("results") or []}  # an older saved run
other |= {c for c in args.other.split(",") if c}
saved_ids = {r.get("conversation_id") for r in run["results"]}

out = {
    "run_at": run["run_at"],
    "voices": sorted({v["voice"] for v in sources.values()}),
    "results": run["results"],
    "other_test_conversations": sorted(c for c in other - saved_ids if c),
}
target.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
print(f"saved {len(run['results'])} calls to {target} ({len(out['other_test_conversations'])} other test calls excluded)")
