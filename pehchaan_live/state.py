"""Bounded transient records for the current caller turn and decision receipts."""

from dataclasses import dataclass, field

from .contracts import Decision, Feedback, FeedbackReceipt, FieldDecision, Question, Turn


@dataclass(frozen=True)
class Pending:
    question: Question
    action: str
    expires_at: float


@dataclass(frozen=True)
class CheckReceipt:
    fingerprint: str
    decision: Decision


@dataclass
class Session:
    policy_sha256: str
    expires_at: float
    invalidated: bool = False
    turn: Turn | None = None
    turn_decision: Decision | None = None
    evidence: dict[str, FieldDecision] = field(default_factory=dict)
    evidence_at: dict[str, float] = field(default_factory=dict)
    readback_action: str | None = None
    turn_digests: dict[str, tuple[int, str]] = field(default_factory=dict)
    asked_actions: frozenset[str] = frozenset()
    pending: Pending | None = None
    answers: dict[str, str] = field(default_factory=dict)
    checks: dict[str, CheckReceipt] = field(default_factory=dict)
    decision_questions: dict[str, str | None] = field(default_factory=dict)
    feedback: dict[str, tuple[Feedback, FeedbackReceipt]] = field(default_factory=dict)
