"""Independent exact-outcome scoring, grouped slices and a paired cluster bootstrap."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable
from statistics import mean

from pehchaan_live.settings import live_settings

from .dataset import Opportunity
from .replay import Outcome

Rates = dict[str, float | int | None]


def quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def wrong(row: Opportunity, outcome: Outcome) -> bool:
    return outcome.arguments is not None and outcome.arguments != row.expected


def completion(row: Opportunity, outcome: Outcome) -> bool:
    return row.expected is not None and outcome.arguments == row.expected


def measures(rows: list[Opportunity], outcomes: list[Outcome]) -> Rates:
    pairs = list(zip(rows, outcomes, strict=True))
    n = len(pairs)
    valid = sum(row.expected is not None for row in rows)
    wrong_allowed = sum(wrong(row, result) for row, result in pairs)
    completed = sum(completion(row, result) for row, result in pairs)
    latency = [ms for result in outcomes for ms in result.latency_ms]
    inference_cost = [result.cost_usd for result in outcomes]
    return {
        "opportunities": n, "clusters": len({row.cluster for row in rows}), "eligible_completions": valid,
        "wrong_allowed": wrong_allowed, "wrong_allowed_per_1000": 1000 * wrong_allowed / n,
        "correct_completion": completed, "correct_completion_rate": completed / valid if valid else None,
        "correct_after_clarification": sum(completion(row, result) and result.questions > 0 for row, result in pairs),
        "missed_fields": sum(len(set(row.expected or {}) - result.fields) for row, result in pairs),
        "questions": sum(result.questions for result in outcomes),
        "unnecessary_questions": sum(result.questions for row, result in pairs if not row.question_needed),
        "deferrals": sum(result.arguments is None for result in outcomes),
        "protected_substitutions": sum(result.arguments is not None and result.arguments != result.authorized_input
                                       for result in outcomes),
        "added_p50_ms": quantile(latency, 0.5), "added_p95_ms": quantile(latency, 0.95),
        "cost_per_1000_checks": 1000 * mean(inference_cost) if None not in inference_cost else None,
    }


def slices(rows: list[Opportunity], outcomes: list[Outcome]) -> dict:
    keys: dict[str, Callable] = {
        "field": lambda row: row.field,
        "workflow": lambda row: row.policy,
        "language": lambda row: row.language,
        "noise": lambda row: row.noise,
        "provider": lambda row: f"{row.provider.name}/{row.provider.model}/{row.provider.version}" if row.provider else "unspecified",
    }
    report = {}
    for label, key in keys.items():
        grouped = defaultdict(list)
        for index, row in enumerate(rows):
            grouped[key(row)].append(index)
        report[label] = {
            tag: measures([rows[i] for i in indexes], [outcomes[i] for i in indexes])
            for tag, indexes in sorted(grouped.items())
        }
    return report


def paired(rows: list[Opportunity], baseline: list[Outcome], challenger: list[Outcome]) -> dict:
    strata = defaultdict(list)
    for row, control, treatment in zip(rows, baseline, challenger, strict=True):
        strata[row.cluster].append((int(wrong(row, control)) - int(wrong(row, treatment)),
                                    int(completion(row, treatment)) - int(completion(row, control)),
                                    int(row.expected is not None)))
    totals = [tuple(map(sum, zip(*group, strict=True))) + (len(group),) for group in strata.values()]
    if len(totals) < 2:
        return {"independent_clusters": len(totals), "wrong_reduction_per_1000_ci95": None, "completion_delta_ci95": None}
    rng = random.Random(20261127)
    differences, completions = [], []
    for _ in range(live_settings()["benchmark"]["bootstrap_samples"]):
        wrong_delta, completion_delta, eligible, count = map(sum, zip(*rng.choices(totals, k=len(totals)), strict=True))
        differences.append(1000 * wrong_delta / count)
        if eligible:
            completions.append(completion_delta / eligible)
    return {
        "independent_clusters": len(totals),
        "wrong_reduction_per_1000_ci95": [quantile(differences, p) for p in (0.025, 0.975)],
        "completion_delta_ci95": [quantile(completions, p) for p in (0.025, 0.975)] if completions else None,
    }
