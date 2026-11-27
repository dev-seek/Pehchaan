"""Manage tenant policy revisions after independently checked evaluation and approval."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
from pathlib import Path
from typing import Literal

from pydantic import Field

from pehchaan_live.contracts import Contract, Identifier
from pehchaan_live.policy import load_policy
from pehchaan_live.rollout import Revision, Rollout, pinned_policy, read_rollout
from pehchaan_live.runtime import digest
from pehchaan_live.settings import live_settings


class Evaluation(Contract):
    tenant: Identifier
    incumbent_sha256: str
    candidate_sha256: str
    evidence_ref: Identifier
    phase: Literal["sealed", "shadow", "canary"]
    opportunities: int = Field(gt=0)
    baseline_wrong: int = Field(ge=0)
    candidate_wrong: int = Field(ge=0)
    reduction_ci95_low_per_1000: float
    completion_delta: float = Field(ge=-1, le=1)
    p95_added_ms: float = Field(ge=0)
    deadline_breaches: int = Field(ge=0)
    invariant_breaches: int = Field(ge=0)
    other_budget_breaches: int = Field(ge=0)


def passed(evidence: Evaluation) -> bool:
    cfg = live_settings()
    return (
        evidence.baseline_wrong > 0
        and evidence.baseline_wrong <= evidence.opportunities
        and evidence.candidate_wrong <= evidence.opportunities
        and (evidence.baseline_wrong - evidence.candidate_wrong) / evidence.baseline_wrong
        >= cfg["benchmark"]["min_relative_improvement"]
        and evidence.reduction_ci95_low_per_1000 > 0
        and evidence.completion_delta >= -cfg["benchmark"]["max_completion_loss"]
        and evidence.p95_added_ms <= cfg["runtime"]["target_p95_ms"]
        and not (evidence.invariant_breaches or evidence.deadline_breaches or evidence.other_budget_breaches)
    )


def transition(
    state: Rollout, operation: str, proof: Evaluation, proof_sha: str, *,
    candidate: Revision | None = None, approval: str | None = None, percent: int = 0,
) -> Rollout:
    if proof.tenant != state.tenant or proof.incumbent_sha256 != state.approved.sha256:
        raise ValueError("evidence must identify this tenant and its current approved revision")
    candidate = candidate or state.candidate
    if not candidate or candidate.sha256 != proof.candidate_sha256 or candidate.sha256 == state.approved.sha256:
        raise ValueError("evidence must identify a distinct candidate")
    update = {"candidate": candidate, "evidence_sha256": proof_sha}
    if operation == "shadow" and state.phase in {"active", "paused"} and proof.phase == "sealed" and passed(proof):
        update |= {"phase": "shadow", "approval_ref": None}
    elif operation == "canary" and state.phase == "shadow" and proof.phase == "shadow" and passed(proof) and approval:
        update |= {"phase": "canary", "approval_ref": approval, "canary_percent": percent}
    elif operation == "monitor" and state.phase == proof.phase == "canary":
        if not passed(proof):
            update |= {"phase": "paused", "canary_percent": 0}
    elif operation == "approve" and state.phase == proof.phase == "canary" and passed(proof) and approval:
        update |= {"phase": "active", "approved": candidate, "previous": state.approved,
                   "candidate": None, "canary_percent": 0, "approval_ref": approval}
    else:
        raise ValueError("transition requires a matching evaluation and any required human approval")
    return Rollout.model_validate(state.model_dump() | update)


def _write(path: Path, state: Rollout, *, first_write: bool = False) -> None:
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        temporary = Path(handle.name)
        try:
            handle.write(state.model_dump_json(indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            if first_write:
                os.link(temporary, path)
            else:
                os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _revision(path: Path) -> Revision:
    return Revision(path=str(path.resolve()), sha256=digest(load_policy(path)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("init", "shadow", "canary", "monitor", "approve", "rollback"))
    parser.add_argument("state", type=Path)
    parser.add_argument("--tenant")
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--approve-ref")
    parser.add_argument("--percent", type=int, default=0)
    args = parser.parse_args()
    lock = args.state.with_name(args.state.name + ".lock")
    with lock.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        _apply(args, parser)


def _apply(args, parser) -> None:
    if args.operation == "init":
        if not args.tenant or not args.policy:
            parser.error("init requires --tenant and --policy")
        state = Rollout(tenant=args.tenant, approved=_revision(args.policy))
        _write(args.state, state, first_write=True)
        return
    state = read_rollout(args.state)
    if args.operation == "rollback":
        if not args.approve_ref:
            parser.error("rollback requires --approve-ref")
        approved = state.approved if state.phase in {"shadow", "canary", "paused"} else state.previous
        if approved is None:
            parser.error("there is no previous approved revision")
        pinned_policy((args.state.parent / approved.path).resolve(), approved.sha256)
        state = Rollout(tenant=state.tenant, approved=approved, phase="paused", approval_ref=args.approve_ref,
                        previous=state.previous if approved == state.approved else None)
    else:
        if not args.evidence:
            parser.error("the transition requires independent evaluation evidence")
        data = args.evidence.read_bytes()
        state = transition(state, args.operation, Evaluation.model_validate_json(data), hashlib.sha256(data).hexdigest(),
                           candidate=_revision(args.policy) if args.operation == "shadow" and args.policy else None,
                           approval=args.approve_ref, percent=args.percent)
    _write(args.state, state)
    print(f"{state.tenant}: {state.phase}")


if __name__ == "__main__":
    main()
