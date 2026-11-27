"""Read an operator-controlled tenant policy pointer and choose a stable canary cohort."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .contracts import Contract, Identifier
from .policy import Policy, load_policy
from .runtime import digest


class Revision(Contract):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Rollout(Contract):
    tenant: Identifier
    approved: Revision
    previous: Revision | None = None
    candidate: Revision | None = None
    phase: Literal["active", "shadow", "canary", "paused"] = "active"
    canary_percent: int = Field(default=0, ge=0, le=100)
    approval_ref: Identifier | None = None
    evidence_sha256: str | None = None

    @model_validator(mode="after")
    def validate_phase(self):
        if self.phase in {"shadow", "canary"} and (not self.candidate or not self.evidence_sha256):
            raise ValueError("shadow and canary require a pinned candidate and evaluation")
        if self.phase == "canary" and (not self.approval_ref or not 0 < self.canary_percent < 100):
            raise ValueError("canary requires approval and a restricted cohort")
        if self.phase != "canary" and self.canary_percent:
            raise ValueError("only canaries may route a fraction of calls")
        return self


def read_rollout(path: Path) -> Rollout:
    return Rollout.model_validate_json(path.read_bytes())


@lru_cache(maxsize=128)
def pinned_policy(path: Path, expected_sha256: str) -> Policy:
    policy = load_policy(path)
    if digest(policy) != expected_sha256:
        raise ValueError("tenant policy differs from the reviewed revision")
    return policy


def selected_policy(path: Path, tenant: str, call_id: str) -> Policy:
    state = read_rollout(path)
    if state.tenant != tenant:
        raise ValueError("rollout tenant mismatch")
    bucket = int.from_bytes(hashlib.sha256(f"{tenant}/{call_id}".encode()).digest()[:8], "big") % 100
    revision = state.candidate if state.phase == "canary" and bucket < state.canary_percent else state.approved
    return pinned_policy((path.parent / revision.path).resolve(), revision.sha256)
