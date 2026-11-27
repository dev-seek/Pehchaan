"""Run a call's state transitions under a deadline and tenant boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from threading import Lock
from time import monotonic

from .contracts import Action, Decision, Feedback, FeedbackReceipt, Turn
from .decisions import action_for_step, check, decision, eligible_field, has_bound_answer, next_question
from .evidence import evaluate, readback, unresolved
from .policy import Policy
from .settings import live_settings
from .state import CheckReceipt, Session


class Refused(ValueError):
    def __init__(self, reason: str, status: int = 409):
        super().__init__(reason)
        self.status = status


def digest(model) -> str:
    encoded = json.dumps(model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def record_decision(session: Session, result: Decision) -> dict[str, str | None]:
    return {**session.decision_questions, result.decision_id: result.question.id if result.question else None}


class LiveHarness:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.config = live_settings()["runtime"]
        self._sessions: dict[tuple[str, str], Session] = {}
        self._lock = Lock()

    def _begin(self, deadline: float | None) -> tuple[float, float]:
        start = self.clock()
        deadline = (
            min(deadline, start + self.config["deadline_ms"] / 1000)
            if deadline is not None
            else (start + self.config["deadline_ms"] / 1000)
        )
        if deadline <= start or not self._lock.acquire(timeout=max(0, deadline - start)):
            raise Refused("deadline_exceeded", 503)
        return start, deadline

    def _finish(self, deadline: float) -> None:
        if self.clock() >= deadline:
            raise Refused("deadline_exceeded", 503)

    def _session(self, tenant: str, call_id: str, policy: Policy, *, create: bool = False) -> Session | None:
        now = self.clock()
        key = (tenant, call_id)
        session = self._sessions.get(key)
        signature = digest(policy)
        if session and session.expires_at > now:
            if session.invalidated or session.policy_sha256 != signature:
                self._sessions[key] = Session(signature, session.expires_at, invalidated=True)
                raise Refused("policy_version_changed")
            return replace(session)
        if not create:
            return None
        expired = [key for key, current in self._sessions.items() if current.expires_at <= now]
        for key in expired:
            del self._sessions[key]
        if sum(scope == tenant for scope, _ in self._sessions) >= self.config["max_calls_per_tenant"]:
            raise Refused("tenant_call_quota", 429)
        return Session(signature, now + self.config["session_seconds"])

    def _publish(self, tenant: str, call_id: str, session: Session, result: Decision, start, deadline) -> Decision:
        self._finish(deadline)
        self._sessions[tenant, call_id] = session
        return result.model_copy(update={"latency_ms": round((self.clock() - start) * 1000, 3)}, deep=True)

    def _update_turn(self, current: Session, turn: Turn, policy: Policy, now: float) -> None:
        pending = current.pending
        reply = pending and turn.reply_to == pending.question.id
        step_changed = reply and turn.step is not None and (
            action_for_step(policy, turn.step) != pending.action or (
                current.turn.step is not None and current.turn.step != turn.step
            )
        )
        fresh_reply = reply and pending.expires_at > now and not step_changed
        if fresh_reply:
            current.evidence = {
                **current.evidence,
                pending.question.field: readback(turn, pending.question.field, policy),
            }
            current.evidence_at = {**current.evidence_at, pending.question.field: now}
            current.readback_action = pending.action
            if current.evidence[pending.question.field].status == "supported":
                current.answers = {**current.answers, pending.question.id: turn.turn_id}
        elif turn.reply_to:
            current.evidence = {name: unresolved(name, "unknown_or_stale_question") for name in policy.fields}
            current.evidence_at = {}
            current.readback_action = pending.action if reply else None
        else:
            current.evidence = {name: evaluate(turn, name, policy) for name in policy.fields}
            current.evidence_at = dict.fromkeys(policy.fields, now)
            current.readback_action = None
        current.turn = turn
        current.pending = None

    def turn(self, tenant: str, policy: Policy, turn: Turn, *, deadline: float | None = None) -> Decision:
        if turn.status == "partial":
            return decision(policy, turn, "ignored", "partial_turn")
        start, deadline = self._begin(deadline)
        try:
            active = self._session(tenant, turn.call_id, policy, create=turn.sequence == 1)
            if active is None:
                raise Refused("unknown_call_or_sequence")
            fingerprint = digest(turn)
            prior = active.turn_digests.get(turn.turn_id)
            if prior:
                if prior != (turn.sequence, fingerprint):
                    raise Refused("turn_id_conflict")
                if active.turn.turn_id != turn.turn_id:
                    return decision(policy, turn, "review", "stale_turn")
                result = active.turn_decision
                if result.question and (active.pending is None or active.pending.expires_at <= self.clock()):
                    return decision(policy, turn, "review", "question_no_longer_active")
                return self._publish(tenant, turn.call_id, active, result, start, deadline)
            if turn.sequence != (active.turn.sequence + 1 if active.turn else 1):
                raise Refused("out_of_order_turn")
            if len(active.turn_digests) >= self.config["max_turns_per_call"]:
                raise Refused("call_turn_quota", 429)
            now = self.clock()
            self._update_turn(active, turn, policy, now)
            result = self._turn_decision(active, turn, policy, now)
            active.turn_decision = result
            active.turn_digests = {**active.turn_digests, turn.turn_id: (turn.sequence, fingerprint)}
            active.decision_questions = record_decision(active, result)
            return self._publish(tenant, turn.call_id, active, result, start, deadline)
        finally:
            self._lock.release()

    def _turn_decision(self, session: Session, turn: Turn, policy: Policy, now: float) -> Decision:
        action = session.readback_action or action_for_step(policy, turn.step)
        if turn.status == "interrupted":
            return decision(policy, turn, "review", "turn_interrupted", action=action)
        if turn.reply_to and not has_bound_answer(session):
            return decision(policy, turn, "review", "readback_unavailable", action=action)
        if turn.step is not None and not action_for_step(policy, turn.step):
            return decision(policy, turn, "review", "unknown_workflow_step")
        names = policy.actions[action].required if action else list(policy.fields)
        fields = [eligible_field(session, name, action, now, policy) for name in names]
        if action and any(field.status != "supported" for field in fields):
            reason, question = next_question(session, policy, action, fields, now)
            return decision(
                policy, turn, "ask" if question else "review", reason, fields=fields, action=action, question=question
            )
        return decision(policy, turn, "recorded", "caller_turn_recorded", action=action, fields=fields)

    def action(self, tenant: str, policy: Policy, proposed: Action, *, deadline: float | None = None) -> Decision:
        start, deadline = self._begin(deadline)
        try:
            active = self._session(tenant, proposed.call_id, policy)
            if not active:
                return decision(policy, proposed, "review", "unknown_or_expired_call", action=proposed.action)
            prior = active.checks.get(proposed.idempotency_key)
            fingerprint = digest(proposed)
            if prior and prior.fingerprint != fingerprint:
                raise Refused("idempotency_key_conflict")
            if active.turn.turn_id != proposed.turn_id:
                return decision(policy, proposed, "review", "stale_turn", action=proposed.action)
            now = self.clock()
            if prior:
                if prior.decision.outcome == "allow" and (
                    active.pending
                    or any(
                        start - active.evidence_at[field.field] >= policy.evidence_seconds
                        for field in prior.decision.fields
                    )
                ):
                    return decision(policy, proposed, "review", "authorization_expired", action=proposed.action)
                if prior.decision.outcome == "ask" and (not active.pending or active.pending.expires_at <= now):
                    return decision(policy, proposed, "review", "question_no_longer_active", action=proposed.action)
                return self._publish(tenant, proposed.call_id, active, prior.decision, start, deadline)
            if len(active.checks) >= self.config["max_checks_per_call"]:
                raise Refused("call_action_quota", 429)
            result = check(active, proposed, policy, now)
            active.checks = {**active.checks, proposed.idempotency_key: CheckReceipt(fingerprint, result)}
            active.decision_questions = record_decision(active, result)
            return self._publish(tenant, proposed.call_id, active, result, start, deadline)
        finally:
            self._lock.release()

    def feedback(
        self,
        tenant: str,
        policy: Policy,
        event: Feedback,
        *,
        can_review: bool = False,
        deadline: float | None = None,
    ) -> FeedbackReceipt:
        if event.kind != "clarification" and not can_review:
            raise Refused("review_credential_required", 403)
        _, deadline = self._begin(deadline)
        try:
            active = self._session(tenant, event.call_id, policy)
            if not active or event.decision_id not in active.decision_questions:
                raise Refused("unknown_decision", 404)
            prior = active.feedback.get(event.feedback_id)
            if prior:
                if prior[0] != event:
                    raise Refused("feedback_id_conflict")
                return prior[1].model_copy(deep=True)
            if len(active.feedback) >= self.config["max_feedback_per_call"]:
                raise Refused("call_feedback_quota", 429)
            source = {"clarification": "caller_readback", "review": "authorized_review", "outcome": "checked_outcome"}
            if event.kind == "clarification":
                question_id = active.decision_questions[event.decision_id]
                if active.answers.get(question_id) != event.answer_turn_id:
                    raise Refused("answer_not_bound_to_decision")
            receipt = FeedbackReceipt(
                feedback_id=event.feedback_id,
                decision_id=event.decision_id,
                source=source[event.kind],
                answer_turn_id=event.answer_turn_id,
                evidence_ref=event.evidence_ref,
                outcome=event.outcome,
            )
            active.feedback = {**active.feedback, event.feedback_id: (event, receipt)}
            self._finish(deadline)
            self._sessions[tenant, event.call_id] = active
            return receipt.model_copy(deep=True)
        finally:
            self._lock.release()

    def delete(self, tenant: str, call_id: str, *, deadline: float | None = None) -> None:
        _, deadline = self._begin(deadline)
        try:
            self._finish(deadline)
            self._sessions.pop((tenant, call_id), None)
        finally:
            self._lock.release()

    def purge_expired(self) -> None:
        with self._lock:
            now = self.clock()
            for key in [key for key, session in self._sessions.items() if session.expires_at <= now]:
                del self._sessions[key]
