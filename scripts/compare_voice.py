"""Compare two voice-test runs (ElevenLabs Sam vs Sam on Deepgram) made with the same clips and conditions.

    .venv/Scripts/python scripts/compare_voice.py voicelab/out/run-<n>.json voicelab/out/run-deepgram-<n>.json [--json out.json]

Every number comes from the two run files: response time is from the end of the caller's speech to Sam's
first audio, measured on the caller's side (voicelab/run.js), the same way for both platforms.
"""
import argparse
import json
import statistics
from pathlib import Path


def load(path: str) -> dict:
    run = json.loads(Path(path).read_text(encoding="utf-8"))
    run["platform"] = run.get("platform") or (run["results"][0].get("platform") if run["results"] else "elevenlabs")
    return run


def median(values: list) -> int | None:
    values = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.median(values)) if values else None


def share(rows: list[dict], key: str) -> str:
    graded = [r for r in rows if r.get(key) is not None]
    return f"{sum(bool(r[key]) for r in graded)}/{len(graded)}" if graded else "—"


def summarize(run: dict) -> dict:
    rows = run["results"]
    numbers = [r for r in rows if r["test"] == "numbers"]
    barge = [r for r in rows if r["test"] == "interruption"]
    silence = [r for r in rows if r["test"] == "silence"]
    by_condition = {}
    for r in numbers:
        by_condition.setdefault(r["condition"], []).append(r)
    return {
        "platform": run["platform"],
        "run_at": run["run_at"],
        "calls": len(rows),
        "response_ms_median": median([r.get("response_ms") for r in numbers]),
        "response_ms_by_condition": {c: median([r.get("response_ms") for r in rs]) for c, rs in by_condition.items()},
        "number_heard": share(numbers, "number_heard"),
        "name_heard": share(numbers, "name_heard"),
        "read_back_right": share(numbers, "read_back_right"),
        "cut_caller_off": share(numbers, "started_before_caller_finished"),
        "barge_in_stopped": share(barge, "stopped"),
        "barge_in_stop_ms_median": median([r.get("stop_ms") for r in barge]),
        "barge_in_passed": share(barge, "passed"),
        "silence_passed": share(silence, "passed"),
        "conversation_ids": [r["conversation_id"] for r in rows if r.get("conversation_id")],
    }


def table(a: dict, b: dict) -> str:
    def ms(v):
        return f"{v / 1000:.2f} s" if isinstance(v, (int, float)) else "—"
    lines = [f"| | {a['platform']} | {b['platform']} |", "| --- | --- | --- |",
             f"| Response time, median (end of caller's speech to Sam's voice) | {ms(a['response_ms_median'])} | {ms(b['response_ms_median'])} |"]
    for cond in a["response_ms_by_condition"]:
        lines.append(f"| … {cond} | {ms(a['response_ms_by_condition'].get(cond))} | {ms(b['response_ms_by_condition'].get(cond))} |")
    for label, key in [("Phone number heard right", "number_heard"), ("Caller's name heard", "name_heard"),
                       ("Number read back right", "read_back_right"), ("Started talking before the caller finished", "cut_caller_off"),
                       ("Stopped when the caller talked over Sam", "barge_in_stopped"), ("Barge-in test passed", "barge_in_passed"),
                       ("Silence test passed (checks in, doesn't hang up)", "silence_passed")]:
        lines.append(f"| {label} | {a[key]} | {b[key]} |")
    lines.append(f"| Time to stop after barge-in, median | {ms(a['barge_in_stop_ms_median'])} | {ms(b['barge_in_stop_ms_median'])} |")
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument("--json")
    args = parser.parse_args()
    a, b = summarize(load(args.first)), summarize(load(args.second))
    print(table(a, b))
    if args.json:
        Path(args.json).write_text(json.dumps({"runs": [a, b]}, indent=1) + "\n", encoding="utf-8")
