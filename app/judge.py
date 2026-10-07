"""How far to trust the AI judge: a person's verdicts on real calls, compared with ElevenLabs' grades.

Labels live in judge_labels.json, written by scripts/label_calls.py. They're keyed by call_ref (a short
fingerprint of the conversation id), so no conversation ids or caller words are kept in the repo.
A label only counts where both the person and the AI gave success or failure; "unknown" on either side
is left out and counted separately.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.analysis_spec import CRITERIA_NAMES
from app.service import call_ref

LABELS = Path(__file__).with_name("judge_labels.json")
VERDICTS = ("success", "failure")
# Below this many comparable verdicts, kappa swings wildly (one answer can move it from 0 to 1), so it's withheld.
MIN_FOR_KAPPA = 20


@lru_cache(maxsize=1)
def labels() -> list[dict]:
    try:
        return json.loads(LABELS.read_text(encoding="utf-8")).get("labels") or []
    except FileNotFoundError:
        return []


def _kappa(pairs: list[tuple[str, str]], min_n: int = MIN_FOR_KAPPA) -> float | None:
    """Cohen's kappa: agreement beyond what chance would give. None when it can't be computed, or when there
    are too few verdicts for it to mean anything."""
    n = len(pairs)
    if n < max(2, min_n):
        return None
    observed = sum(a == b for a, b in pairs) / n
    expected = sum((sum(a == v for a, _ in pairs) / n) * (sum(b == v for _, b in pairs) / n) for v in VERDICTS)
    return None if expected >= 1 else round((observed - expected) / (1 - expected), 2)


def agreement(calls: dict[str, dict], given: list[dict] | None = None) -> dict:
    """calls: conversation_id -> ns_calls row (with evaluation.results)."""
    given = labels() if given is None else given
    if not given:
        return {"status": "none"}
    ai_by_ref = {}
    for cid, c in calls.items():
        results = ((c.get("evaluation") or {}).get("results") or {}) if isinstance(c.get("evaluation"), dict) else {}
        ai_by_ref[call_ref(cid)] = {k: (v or {}).get("result") for k, v in results.items()}
    per: dict[str, list[tuple[str, str]]] = {}
    unknown, disagreements = 0, []
    for lab in given:
        ai = ai_by_ref.get(lab["call_ref"], {}).get(lab["criterion"])
        human = lab.get("human")
        if ai not in VERDICTS or human not in VERDICTS:
            unknown += 1
            continue
        per.setdefault(lab["criterion"], []).append((human, ai))
        if ai != human:
            disagreements.append({"call_ref": lab["call_ref"], "criterion": CRITERIA_NAMES.get(lab["criterion"], lab["criterion"]),
                                  "person": human, "ai": ai, "note": lab.get("note") or ""})
    every = [p for pairs in per.values() for p in pairs]
    return {
        "status": "ok" if every else "none",
        "n": len(every),
        "agree": sum(a == b for a, b in every),
        "rate": round(100 * sum(a == b for a, b in every) / len(every)) if every else None,
        "kappa": _kappa(every),
        "kappa_min": MIN_FOR_KAPPA,
        "calls": len({lab["call_ref"] for lab in given}),
        "left_out": unknown,
        "criteria": [{"criterion": CRITERIA_NAMES.get(k, k), "n": len(v), "agree": sum(a == b for a, b in v),
                      "rate": round(100 * sum(a == b for a, b in v) / len(v)), "kappa": _kappa(v)}
                     for k, v in sorted(per.items())],
        "disagreements": disagreements[:10],
    }
