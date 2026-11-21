"""
Clip-by-clip comparison of the locked exam: the keyword transcript against Pehchaan on the same clips.

Publishes counts only, never exam text. This view was chosen after the exam results were seen, so it is labelled post hoc.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from pehchaan.config import ROOT, settings

CRITICAL = frozenset({"PHONE", "PIN", "AMOUNT"})
LEVELS = ("C3", "C4")


def _silent(row: dict, types: frozenset[str] | None = None) -> int:
    return sum(not e["correct"] and not e["flagged"] and (types is None or e["type"] in types) for e in row["entities"])


def _right(row: dict) -> int:
    return sum(e["correct"] for e in row["entities"])


def _rows(run_dir: Path) -> dict[str, dict[str, dict]]:
    out: dict[str, dict[str, dict]] = {}
    for line in (run_dir / "per_clip.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        out.setdefault(row["system"], {})[row["clip_id"]] = row
    return out


def compare(base: dict[str, dict], ours: dict[str, dict], iters: int, seed: int) -> dict:
    clips = sorted(base)
    drops = [_silent(base[c]) - _silent(ours[c]) for c in clips]
    facts = sum(len(base[c]["entities"]) for c in clips)
    rng = random.Random(seed)
    samples = sorted(sum(rng.choice(drops) for _ in clips) / facts for _ in range(iters))
    before, after = sum(_silent(base[c]) for c in clips), sum(_silent(ours[c]) for c in clips)
    return {
        "clips": len(clips),
        "facts": facts,
        "silent_before": before,
        "silent_after": after,
        "silent_drop_share": (before - after) / before if before else None,
        "right_before": sum(_right(base[c]) for c in clips),
        "right_after": sum(_right(ours[c]) for c in clips),
        "critical_facts": sum(e["type"] in CRITICAL for c in clips for e in base[c]["entities"]),
        "critical_silent_before": sum(_silent(base[c], CRITICAL) for c in clips),
        "critical_silent_after": sum(_silent(ours[c], CRITICAL) for c in clips),
        "clips_better": sum(d > 0 for d in drops),
        "clips_worse": sum(d < 0 for d in drops),
        "damaged_edits": sum(ours[c].get("n_damage", 0) for c in clips),
        "drop_ci95_points": [samples[int(0.025 * iters)] * 100, samples[int(0.975 * iters) - 1] * 100],
    }


def build() -> dict | None:
    cfg = settings()
    results = ROOT / cfg["paths"]["results"]
    report = {"note": "Clip-by-clip view chosen after the exam results were seen (post hoc). Counts only.", "lines": {}}
    for clips in cfg["exam"]["conditions"]:
        latest = results / f"latest_{clips}.json"
        if not latest.exists():
            return None
        rows = _rows(ROOT / json.loads(latest.read_text(encoding="utf-8"))["dir"])
        report["lines"][clips] = {
            level: compare(
                rows[f"B1_asr_keywords_{level}"],
                rows[f"P_on_B1_{level}"],
                cfg["bench"]["bootstrap_iters"],
                cfg["bench"]["seed"],
            )
            for level in LEVELS
        }
    return report
