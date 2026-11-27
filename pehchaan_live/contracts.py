"""Version 2 request and decision contracts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,95}$", strict=True)]
Text = Annotated[str, StringConstraints(min_length=1, max_length=4000, strict=True)]
Value = Annotated[str, StringConstraints(min_length=1, max_length=240, strict=True)]
Arguments = dict[Identifier, Value]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Provider(Contract):
    name: Identifier
    model: Identifier
    version: Identifier | None = None
    language: Identifier | None = None


class Turn(Contract):
    call_id: Identifier
    turn_id: Identifier
    sequence: int = Field(ge=1, le=1_000_000)
    transcript: Text | Literal[""]
    status: Literal["finalized", "partial", "interrupted"] = "finalized"
    provider: Provider | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    alternative: Text | None = None
    alternative_provider: Provider | None = None
    alternative_context_free: bool = False
    step: Identifier | None = None
    reply_to: Identifier | None = None


class Action(Contract):
    call_id: Identifier
    turn_id: Identifier
    action: Identifier
    arguments: Arguments = Field(max_length=32)
    idempotency_key: Identifier


class Feedback(Contract):
    call_id: Identifier
    decision_id: Identifier
    feedback_id: Identifier
    kind: Literal["clarification", "review", "outcome"]
    answer_turn_id: Identifier | None = None
    outcome: Literal["correct", "incorrect", "deferred"] | None = None
    evidence_ref: Identifier | None = None

    @model_validator(mode="after")
    def evidence_matches_kind(self):
        if self.kind == "clarification":
            if not self.answer_turn_id or self.outcome or self.evidence_ref:
                raise ValueError("clarification requires only an answer turn")
        elif self.answer_turn_id or not self.outcome or not self.evidence_ref:
            raise ValueError("review and outcome require a disposition and independent evidence reference")
        return self


class Span(Contract):
    turn_id: Identifier
    source: Literal["transcript", "alternative", "readback"]
    start: int
    end: int
    text: str


class FieldDecision(Contract):
    field: Identifier
    status: Literal["supported", "unresolved", "unsupported"]
    value: str | None = None
    reason: str
    spans: list[Span] = Field(default_factory=list)


class Question(Contract):
    id: Identifier
    field: Identifier
    prompt: str


class Decision(Contract):
    decision_id: Identifier | None = None
    call_id: Identifier
    turn_id: Identifier
    policy_id: Identifier
    policy_version: Identifier
    action: Identifier | None = None
    outcome: Literal["allow", "ask", "review", "recorded", "ignored"]
    reason: str
    fields: list[FieldDecision] = Field(default_factory=list)
    question: Question | None = None
    latency_ms: float = 0.0


class FeedbackReceipt(Contract):
    feedback_id: Identifier
    decision_id: Identifier
    source: Literal["caller_readback", "authorized_review", "checked_outcome"]
    answer_turn_id: Identifier | None = None
    outcome: Literal["correct", "incorrect", "deferred"] | None = None
    evidence_ref: Identifier | None = None
