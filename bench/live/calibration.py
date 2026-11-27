"""Search bounded conservative changes on labelled development replay."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

from pehchaan_live.policy import Calibration, Policy
from pehchaan_live.runtime import digest
from pehchaan_live.settings import live_settings

from .dataset import Opportunity
from .replay import Outcome, replay
from .score import measures


@dataclass(frozen=True)
class Candidate:
    name: str
    policies: dict[str, Policy]
    outcomes: list[Outcome]


def evaluate(rows: list[Opportunity], policies: dict[str, Policy], name: str) -> Candidate:
    return Candidate(name, policies, [replay(row, policies[row.policy]) for row in rows])


def _policies(policies: dict[str, Policy], agreement: bool, confidence: float | None, scopes: list[str]):
    revised = {}
    for name, policy in policies.items():
        guarded = [name for name, rule in policy.fields.items() if rule.evidence == "transcript"] if agreement else []
        filters = Calibration(agreement_for=guarded, confidence_floors=dict.fromkeys(scopes, confidence) if confidence else {})
        update = policy.model_copy(update={"calibration": filters})
        revised[name] = update.model_copy(update={"version": f"{policy.version}.dev-{digest(update)[:10]}"})
    return revised


def search(rows: list[Opportunity], policies: dict[str, Policy]) -> tuple[Candidate, list[dict]]:
    config = live_settings()["benchmark"]
    scopes = sorted({f"{p.name}/{p.model}/{p.version}" for row in rows if (p := row.provider) and p.version})
    baseline = evaluate(rows, policies, "incumbent")
    base = measures(rows, baseline.outcomes)
    best = baseline
    rank = (base["wrong_allowed"], -base["correct_completion"], base["questions"], base["deferrals"])
    trials = [{"candidate": best.name, "eligible": True, "metrics": base}]
    options = product((False, True), [None, *config["confidence_grid"]] if scopes else [None])
    for agreement, confidence in list(options)[1:config["max_candidates"]]:
        name = f"agreement={agreement}, confidence={confidence}"
        candidate = evaluate(rows, _policies(policies, agreement, confidence, scopes), name)
        score = measures(rows, candidate.outcomes)
        eligible = (score["correct_completion_rate"] >= base["correct_completion_rate"] - config["max_completion_loss"]
                    and score["questions"] <= base["questions"] and score["deferrals"] <= base["deferrals"]
                    and score["added_p95_ms"] <= live_settings()["runtime"]["target_p95_ms"]
                    and score["cost_per_1000_checks"] <= base["cost_per_1000_checks"]
                    and score["protected_substitutions"] == 0)
        trials.append({"candidate": name, "eligible": eligible, "metrics": score})
        challenger = (score["wrong_allowed"], -score["correct_completion"], score["questions"], score["deferrals"])
        if eligible and challenger < rank:
            best, rank = candidate, challenger
    return best, trials
