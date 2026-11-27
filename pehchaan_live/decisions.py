"""Compare proposed tool arguments and spend each action's clarification budget."""

from uuid import uuid4

from .contracts import Action, Decision, FieldDecision, Question
from .evidence import unresolved
from .policy import ActionRule, Policy
from .state import Pending, Session
from .values import canonical


def action_for_step(policy: Policy, step: str | None) -> str | None:
    return policy.steps.get(step) if step else None


def has_bound_answer(session: Session) -> bool:
    return any(field.reason == "caller_readback" for field in session.evidence.values())


def eligible_field(session: Session, name: str, action: str, now: float, policy: Policy) -> FieldDecision:
    result = session.evidence[name]
    if result.status == "supported":
        if now - session.evidence_at[name] >= policy.evidence_seconds:
            return unresolved(name, "stale_evidence")
        if session.readback_action and session.readback_action != action:
            return unresolved(name, "evidence_bound_to_another_action")
    return result


def fields_for_action(session: Session, action: Action, policy: Policy, now: float) -> list[FieldDecision]:
    fields = []
    rule = policy.actions[action.action]
    for name in [*rule.required, *(name for name in rule.optional if name in action.arguments)]:
        result = eligible_field(session, name, action.action, now, policy)
        if result.status == "supported":
            value = action.arguments.get(name)
            if value is None:
                result = unresolved(name, "missing_proposed_argument", result.spans)
            elif canonical(value, policy.fields[name]) != result.value:
                result = unresolved(name, "proposed_argument_mismatch", result.spans)
        fields.append(result)
    return fields


def next_question(
    session: Session, policy: Policy, action: str, fields: list[FieldDecision], now: float,
) -> tuple[str, Question | None]:
    rule: ActionRule = policy.actions[action]
    unresolved_fields = [field for field in fields if field.status != "supported"]
    if any(field.status == "unsupported" for field in unresolved_fields):
        return "validator_unavailable", None
    if rule.fallback == "review" or any(policy.fields[field.field].fallback == "review" for field in unresolved_fields):
        return "policy_requires_review", None
    if session.turn.status != "finalized":
        return "turn_interrupted", None
    pending = session.pending
    if pending:
        if pending.action == action and pending.expires_at > now:
            return "clarification_required", pending.question
        return "another_clarification_pending", None
    if action in session.asked_actions:
        return "clarification_budget_exhausted", None
    field = unresolved_fields[0].field
    question = Question(id=uuid4().hex, field=field, prompt=policy.fields[field].question)
    session.pending = Pending(question, action, now + policy.evidence_seconds)
    session.asked_actions |= {action}
    return "clarification_required", question


def decision(policy: Policy, request, outcome: str, reason: str, **details) -> Decision:
    return Decision(
        decision_id=uuid4().hex, call_id=request.call_id, turn_id=request.turn_id,
        policy_id=policy.id, policy_version=policy.version, outcome=outcome, reason=reason, **details,
    )


def check(session: Session, action: Action, policy: Policy, now: float) -> Decision:
    name = action.action
    if name not in policy.actions:
        return decision(policy, action, "review", "undeclared_action", action=name)
    if session.turn.status != "finalized":
        return decision(policy, action, "review", "turn_interrupted", action=name)
    if session.turn.reply_to and not has_bound_answer(session):
        return decision(policy, action, "review", "readback_unavailable", action=name)
    if session.turn.step is not None and action_for_step(policy, session.turn.step) != name:
        return decision(policy, action, "review", "action_outside_active_step", action=name)
    if session.readback_action and session.readback_action != name:
        return decision(policy, action, "review", "readback_bound_to_another_action", action=name)
    rule = policy.actions[name]
    if set(action.arguments) - set(rule.required + rule.optional):
        return decision(policy, action, "review", "undeclared_arguments", action=name)
    fields = fields_for_action(session, action, policy, now)
    if all(field.status == "supported" for field in fields) and not session.pending:
        return decision(policy, action, "allow", "arguments_supported", action=name, fields=fields)
    if all(field.status == "supported" for field in fields):
        return decision(policy, action, "review", "clarification_pending", action=name, fields=fields)
    reason, question = next_question(session, policy, name, fields, now)
    return decision(policy, action, "ask" if question else "review", reason, action=name, fields=fields, question=question)
