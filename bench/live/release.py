"""Score a selected candidate against sealed fixtures and a frozen baseline."""

from __future__ import annotations

from pehchaan_live.settings import live_settings

from .dataset import Opportunity
from .replay import Outcome
from .score import measures, paired, slices


def compare(rows: list[Opportunity], outputs: dict[str, list[Outcome]], challenger: str) -> dict:
    scores = {
        name: {"overall": measures(rows, result), "slices": slices(rows, result)}
        for name, result in outputs.items()
    }
    against = {
        name: paired(rows, result, outputs[challenger])
        for name, result in outputs.items() if name != challenger
    }
    return {"systems": scores, "paired_vs_challenger": against}


def gate(report: dict, *, challenger: str, baselines: tuple[str, ...], safety_passed: bool) -> dict:
    cfg = live_settings()
    scores = report["systems"]
    strongest = min(baselines, key=lambda name: (
        scores[name]["overall"]["wrong_allowed"], -scores[name]["overall"]["correct_completion"],
    ))
    base, trial = scores[strongest]["overall"], scores[challenger]["overall"]
    intervals = report["paired_vs_challenger"][strongest]
    ci = intervals["wrong_reduction_per_1000_ci95"]
    relative = (base["wrong_allowed"] - trial["wrong_allowed"]) / base["wrong_allowed"] if base["wrong_allowed"] else None
    failed = []
    if not safety_passed or trial["protected_substitutions"]:
        failed.append("invariant_suite")
    if relative is None or relative < cfg["benchmark"]["min_relative_improvement"] or ci is None or ci[0] <= 0:
        failed.append("insufficient_supported_error_reduction")
    if (trial["correct_completion_rate"] is None or base["correct_completion_rate"] is None
            or trial["correct_completion_rate"] < base["correct_completion_rate"] - cfg["benchmark"]["max_completion_loss"]):
        failed.append("completion_loss")
    if trial["added_p95_ms"] is None or trial["added_p95_ms"] > cfg["runtime"]["target_p95_ms"]:
        failed.append("latency_budget")
    return {"baseline": strongest, "relative_error_reduction": relative, "failed": failed,
            "disposition": "eligible_for_shadow" if not failed else "hold_in_review"}
