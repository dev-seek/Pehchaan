"""
Regression gate: a change is adopted only if it does not break a promise we have already measured.

  python -m bench.gate                  # compare the latest real dev run with the adopted baseline
  python -m bench.gate --adopt --note "why"   # after it passes, make that run the new baseline

The baseline lives in git, so every agent and account is held to the same numbers. Adoption is a deliberate step:
a run never replaces the baseline by itself, and git history is the rollback. Dev only: the exam never enters here.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from pehchaan.config import ROOT, settings


def fact_state(entity: dict) -> str:
    return "correct" if entity["correct"] else "flagged" if entity["flagged"] else "silent"


def snapshot(summary: dict, rows: list[dict], systems: list[str]) -> dict:
    out = {"manifest": summary["manifest"], "n_clips": summary["n_clips"], "systems": {}}
    for sid in systems:
        s = summary["systems"][sid]
        facts = {f"{r['clip_id']}|{e['type']}|{e['value']}": fact_state(e)
                 for r in rows if r["system"] == sid for e in r["entities"]}
        out["systems"][sid] = {"silent_error_rate": s["silent_error_rate"], "entity_accuracy": s["entity_accuracy"],
                               "over_correction_rate": s["over_correction_rate"], "damaged_edits": s["damaged_edits"],
                               "flags_per_clip": s["flags_per_clip"], "facts": facts}
    return out


def compare(baseline: dict, current: dict, flag_tolerance: float) -> list[str]:
    """Every way `current` is worse than `baseline`, in plain words. Empty means it may be adopted."""
    problems = []
    if baseline["n_clips"] != current["n_clips"]:
        problems.append(f"clip count changed: {baseline['n_clips']} -> {current['n_clips']}")
    for sid, old in baseline["systems"].items():
        new = current["systems"].get(sid)
        if new is None:
            problems.append(f"{sid}: missing from this run")
            continue
        for metric in ("silent_error_rate", "over_correction_rate", "damaged_edits"):
            if new[metric] > old[metric]:
                problems.append(f"{sid}: {metric} got worse: {old[metric]:.4g} -> {new[metric]:.4g}")
        if new["flags_per_clip"] > old["flags_per_clip"] + flag_tolerance:
            problems.append(f"{sid}: flags_per_clip rose: {old['flags_per_clip']:.2f} -> {new['flags_per_clip']:.2f}")
        problems += [f"{sid}: now silently wrong: {fact}" for fact, state in new["facts"].items()
                     if state == "silent" and old["facts"].get(fact, "silent") != "silent"]
    return problems


def _load_latest() -> tuple[dict, list[dict]]:
    results = ROOT / settings()["paths"]["results"]
    summary = json.loads((results / "latest_dev.json").read_text(encoding="utf-8"))
    if summary.get("simulated"):
        raise SystemExit("Refusing: the latest run is simulated.")
    lines = (ROOT / summary["dir"] / "per_clip.jsonl").read_text(encoding="utf-8").splitlines()
    return summary, [json.loads(x) for x in lines if x.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adopt", action="store_true")
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    cfg = settings()["bench"]["gate"]
    baseline_file = Path(ROOT / cfg["baseline"])
    summary, rows = _load_latest()
    current = snapshot(summary, rows, cfg["systems"])
    problems = []
    if baseline_file.exists():
        problems = compare(json.loads(baseline_file.read_text(encoding="utf-8")), current, cfg["flags_per_clip_tolerance"])
    for p in problems:
        print("REGRESSION:", p)
    if problems:
        print(f"gate: FAILED with {len(problems)} regression(s)")
        return 1
    print("gate: passed" if baseline_file.exists() else "gate: no baseline yet")
    if a.adopt:
        if not a.note:
            raise SystemExit("--adopt needs --note saying why this run should become the baseline")
        current.update(adopted_at=time.strftime("%Y-%m-%d %H:%M:%S"), note=a.note, run=summary["dir"])
        baseline_file.write_text(json.dumps(current, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        print(f"adopted: {baseline_file.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
