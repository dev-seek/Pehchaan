"""Check independently labelled replays, release metrics and tenant rollout controls."""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from bench.live.calibration import search
from bench.live.dataset import check_splits, load_split, policies_for
from bench.live.release import compare, gate
from bench.live.replay import native, raw, replay
from bench.live.rollout import Evaluation, transition
from bench.live.score import measures, paired
from pehchaan_live.policy import reference_policy
from pehchaan_live.rollout import Revision, Rollout, selected_policy
from pehchaan_live.runtime import digest


def test_split_seals_search_and_transfer_use_declared_policy_only():
    check_splits()
    development, _ = load_split("dev")
    candidate, trials = search(development, policies_for(development))
    assert candidate.name == "incumbent"
    assert any(not trial["eligible"] for trial in trials)
    transfer, _ = load_split("transfer")
    policies = policies_for(transfer)
    results = [replay(row, policies[row.policy]) for row in transfer]
    score = measures(transfer, results)
    assert score["wrong_allowed"] == 0
    assert score["correct_completion_rate"] == 1.0
    assert score["protected_substitutions"] == 0


def test_main_metric_and_paired_intervals_follow_independent_labels():
    rows, _ = load_split("release")
    policies = policies_for(rows)
    outcomes = [replay(row, policies[row.policy]) for row in rows]
    baseline = [native(row) for row in rows]
    comparison = paired(rows, baseline, outcomes)
    assert comparison["independent_clusters"] == 24
    assert comparison["wrong_reduction_per_1000_ci95"][0] > 0
    altered = replace(outcomes[0], authorized_input={"altered": "yes"})
    assert measures(rows, [altered, *outcomes[1:]])["protected_substitutions"] == 1
    report = compare(rows, {"native": baseline, "incumbent": outcomes, "challenger": outcomes,
                            "raw": [raw(row) for row in rows]}, "challenger")
    readiness = gate(report, challenger="challenger", baselines=("native", "incumbent"), safety_passed=True)
    assert readiness["baseline"] == "incumbent" and readiness["disposition"] == "hold_in_review"


def _evidence(tenant: str, incumbent: Revision, candidate: Revision, phase: str, **overrides) -> Evaluation:
    return Evaluation.model_validate({
        "tenant": tenant, "incumbent_sha256": incumbent.sha256, "candidate_sha256": candidate.sha256,
        "evidence_ref": f"audited-{phase}", "phase": phase, "opportunities": 300, "baseline_wrong": 30,
        "candidate_wrong": 10, "reduction_ci95_low_per_1000": 19.0, "completion_delta": -0.01,
        "p95_added_ms": 108.0, "deadline_breaches": 0, "invariant_breaches": 0, "other_budget_breaches": 0,
    } | overrides)


def _policy_files(path: Path):
    policy = reference_policy("delivery")
    candidate = policy.model_copy(update={"version": "2.0.0"})
    for name, revision in (("stable", policy), ("candidate", candidate)):
        (path / f"{name}.yaml").write_text(yaml.safe_dump(revision.model_dump()), encoding="utf-8")
    return Revision(path="stable.yaml", sha256=digest(policy)), Revision(path="candidate.yaml", sha256=digest(candidate))


def test_rollout_requires_review_and_pauses_to_approved_revision(tmp_path):
    incumbent, candidate = _policy_files(tmp_path)
    state = Rollout(tenant="alpha", approved=incumbent)
    prior = _evidence("alpha", incumbent, candidate, "sealed")
    with pytest.raises(ValueError, match="matching evaluation"):
        transition(state, "shadow", prior.model_copy(update={"baseline_wrong": 0}), "sealed-digest", candidate=candidate)
    shadow = transition(state, "shadow", prior, "sealed-digest", candidate=candidate)
    checked = _evidence("alpha", incumbent, candidate, "shadow")
    with pytest.raises(ValueError, match="approval"):
        transition(shadow, "canary", checked, "shadow-digest", percent=30)
    path = tmp_path / "release.json"
    path.write_text(shadow.model_dump_json())
    assert selected_policy(path, "alpha", "call-1").version == "1.0.0"
    canary = transition(shadow, "canary", checked, "shadow-digest", approval="review-586", percent=30)
    path.write_text(canary.model_dump_json())
    cohorts = {selected_policy(path, "alpha", f"call-{i}").version for i in range(50)}
    assert cohorts == {"1.0.0", "2.0.0"}
    with pytest.raises(ValueError, match="tenant mismatch"):
        selected_policy(path, "beta", "call-1")
    bad = _evidence("alpha", incumbent, candidate, "canary", invariant_breaches=1)
    paused = transition(canary, "monitor", bad, "warning-digest")
    path.write_text(paused.model_dump_json())
    assert paused.phase == "paused" and paused.canary_percent == 0
    assert all(selected_policy(path, "alpha", f"call-{i}").version == "1.0.0" for i in range(50))
    passed = _evidence("alpha", incumbent, candidate, "canary")
    approved = transition(canary, "approve", passed, "verification-digest", approval="change-875")
    assert approved.approved == candidate and approved.previous == incumbent
