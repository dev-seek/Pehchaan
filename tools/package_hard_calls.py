"""
Package the sealed adversarial result for the site. Totals only, from saved runs, with no model call.

    python tools/package_hard_calls.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.adversarial import RUNS, load, totals  # noqa: E402
from pehchaan.config import ROOT  # noqa: E402

STEPS = (
    ("engine_alone", "Core engine"),
    ("live_453c13d", "First meaning check"),
    ("cf1ff63", "Pehchaan today"),
)
OUTPUT = ROOT / "data/published/hard_calls.json"


def build() -> dict:
    cases = load("holdout")
    steps = []
    for run, label in STEPS:
        answers = json.loads((RUNS / f"holdout_{run}.json").read_text(encoding="utf-8"))
        steps.append({"id": run, "label": label, **totals(cases, answers)})
    return {
        "note": "Written by a separate AI, sealed before the fix, each system scored once. Generated text, not the exam.",
        "calls": len(cases),
        "steps": steps,
        "stress": json.loads((ROOT / "data/published/stress.json").read_text(encoding="utf-8")),
    }


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), indent=1) + "\n", encoding="utf-8")
    print("packaged", OUTPUT.name)
