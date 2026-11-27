"""Load labelled action opportunities with checks for leakage between splits."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field

from pehchaan.config import ROOT
from pehchaan_live.contracts import Arguments, Contract, Provider, Turn
from pehchaan_live.policy import Policy, load_policy, reference_policy

DATA = ROOT / "data" / "bench" / "live"


class Opportunity(Contract):
    id: str
    cluster: str
    family: str
    policy: str
    step: str
    action: str
    field: str
    language: str
    noise: str
    provider: Provider | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    transcript: str
    alternative: str | None = None
    proposed: Arguments
    expected: Arguments | None
    question_needed: bool
    cms_context: Arguments = Field(default_factory=dict)
    early: bool = False
    correction: str | None = None
    reply: str | None = None
    reply_status: Literal["finalized", "interrupted"] = "finalized"
    retry_arguments: Arguments | None = None
    native_arguments: Arguments | None = None


def read(path: Path) -> list[Opportunity]:
    rows = [Opportunity.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows or len({row.id for row in rows}) != len(rows):
        raise ValueError("dataset must have distinct action opportunities")
    return rows


def load_split(split: str) -> tuple[list[Opportunity], str]:
    if split not in {"dev", "release", "transfer"}:
        raise ValueError("unknown action benchmark split")
    filename = DATA / f"{split}.jsonl"
    digest = hashlib.sha256(filename.read_bytes()).hexdigest()
    if split != "dev" and digest != filename.with_suffix(".sha256").read_text(encoding="utf-8").strip():
        raise ValueError(f"{split} dataset does not match its seal")
    return read(filename), digest


def _values(rows: list[Opportunity]) -> set[tuple[str, str]]:
    return {
        (field, value)
        for row in rows
        for args in (row.proposed, row.expected, row.retry_arguments, row.native_arguments)
        for field, value in (args or {}).items()
    }


def check_splits() -> None:
    splits = {name: load_split(name)[0] for name in ("dev", "release", "transfer")}
    for left, right in (("dev", "release"), ("dev", "transfer"), ("release", "transfer")):
        for attr in ("id", "family", "cluster"):
            if {getattr(row, attr) for row in splits[left]} & {getattr(row, attr) for row in splits[right]}:
                raise ValueError(f"{attr} overlaps between {left} and {right}")
        if _values(splits[left]) & _values(splits[right]):
            raise ValueError(f"action values overlap between {left} and {right}")
    trained_workflows = {row.policy for row in splits["dev"]}
    if trained_workflows & {row.policy for row in splits["transfer"]}:
        raise ValueError("transfer workflow appears in development")


def policies_for(rows: list[Opportunity]) -> dict[str, Policy]:
    return {
        name: load_policy(DATA / "transfer_policy.yaml") if name == "parcel_pickup" else reference_policy(name)
        for name in sorted({row.policy for row in rows})
    }


def finalized(row: Opportunity, *, transcript: str | None = None, sequence: int = 1) -> Turn:
    return Turn(
        call_id=row.id, turn_id=f"turn-{sequence}", sequence=sequence,
        transcript=transcript if transcript is not None else row.transcript, step=row.step,
        provider=row.provider, confidence=row.confidence if sequence == 1 else None,
        alternative=row.alternative if sequence == 1 else None,
        alternative_provider=row.provider if row.alternative and sequence == 1 else None,
        alternative_context_free=bool(row.alternative and sequence == 1),
    )
