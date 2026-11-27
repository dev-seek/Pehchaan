"""Safety invariants for policy scopes, caller turns and exact tool checks."""

from dataclasses import dataclass

import pytest

from pehchaan_live.contracts import Action, Feedback, Provider, Turn
from pehchaan_live.policy import Policy, reference_policy
from pehchaan_live.runtime import LiveHarness, Refused
from pehchaan_live.values import canonical

DELIVERY = reference_policy("delivery")
APPOINTMENT = reference_policy("appointment")
ORIGINAL = "Order ID I-728; callback number 9006790001"
ARGS = {"order_id": "I-728", "callback_phone": "9006790001"}


@dataclass
class Clock:
    now: float = 100.0

    def __call__(self):
        return self.now


def turn(text=ORIGINAL, n=1, **kwargs):
    return Turn(call_id="same-call", turn_id=f"turn-{n}", sequence=n, transcript=text, **kwargs)


def check(n=1, arguments=None, key="first", action="update_callback"):
    return Action(call_id="same-call", turn_id=f"turn-{n}", action=action,
                  arguments=ARGS if arguments is None else arguments, idempotency_key=key)


def test_correction_prevents_wrong_write_and_receipts_are_idempotent():
    harness = LiveHarness()
    first = harness.turn("tenant", DELIVERY, turn(step="callback"))
    duplicate = harness.turn("tenant", DELIVERY, turn(step="callback"))
    assert first.outcome == "ask" and first.question == duplicate.question
    assert duplicate.decision_id == first.decision_id
    for item in first.fields:
        for span in item.spans:
            assert ORIGINAL[span.start:span.end] == span.text
    initial_check = harness.action("tenant", DELIVERY, check())
    assert initial_check.outcome == "ask" and initial_check.question == first.question
    answer = turn("Callback number 9006790002.", 2, step="callback", reply_to=first.question.id)
    assert harness.turn("tenant", DELIVERY, answer).outcome == "recorded"
    assert harness.action("tenant", DELIVERY, check()).reason == "stale_turn"
    assert harness.action("tenant", DELIVERY, check(2, key="old-number")).outcome == "review"
    exact = ARGS | {"callback_phone": "9006790002"}
    allowed = harness.action("tenant", DELIVERY, check(2, exact, "new-number"))
    assert allowed.outcome == "allow"
    assert [field.value for field in allowed.fields] == ["9006790002", "I-728"]
    assert harness.action("tenant", DELIVERY, check(2, exact, "new-number")).decision_id == allowed.decision_id
    with pytest.raises(Refused, match="idempotency_key_conflict"):
        harness.action("tenant", DELIVERY, check(2, ARGS, "new-number"))
    harness.turn("tenant", DELIVERY, turn("Cancel that.", 3, step="callback"))
    assert harness.action("tenant", DELIVERY, check(2, exact, "new-number")).reason == "stale_turn"
    assert harness.action("tenant", DELIVERY, check(3, exact, "after-cancel")).outcome == "review"


@pytest.mark.parametrize("text,status", [("9006790001", "interrupted"), ("yes", "finalized"), (
    "9006790001 or 9006790002", "finalized"), ("9006790001; callback number 9006790002", "finalized")])
def test_unverified_readback_spends_single_question(text, status):
    harness = LiveHarness()
    first = harness.turn("tenant", DELIVERY, turn(step="callback"))
    assert harness.turn("tenant", DELIVERY, turn(text, 2, status=status, reply_to=first.question.id)).outcome == "review"
    result = harness.action("tenant", DELIVERY, check(2, key="after-question"))
    assert result.outcome == "review" and result.question is None


def test_partial_and_early_tool_calls_do_not_create_authority():
    harness = LiveHarness()
    assert harness.turn("tenant", DELIVERY, turn(status="partial")).outcome == "ignored"
    assert harness.action("tenant", DELIVERY, check()).reason == "unknown_or_expired_call"
    with pytest.raises(Refused, match="unknown_call_or_sequence"):
        harness.turn("tenant", DELIVERY, turn(n=2))
    assert harness.turn("tenant", DELIVERY, turn()).outcome == "recorded"
    assert harness.action("tenant", DELIVERY, check()).outcome == "ask"


def test_stale_answers_and_active_step_scope():
    clock = Clock()
    harness = LiveHarness(clock)
    first = harness.turn("tenant", DELIVERY, turn(step="callback"))
    clock.now += DELIVERY.evidence_seconds
    assert harness.turn("tenant", DELIVERY, turn(step="callback")).reason == "question_no_longer_active"
    answer = harness.turn("tenant", DELIVERY, turn("9006790001", 2, reply_to=first.question.id))
    assert answer.outcome == "review"
    assert harness.action("tenant", DELIVERY, check(2, key="expired")).outcome == "review"
    new = harness.turn("tenant", DELIVERY, turn("Order ID I-728; PIN code 520083", 3, step="address"))
    assert new.question.field == "postal_code"
    assert harness.action("tenant", DELIVERY, check(3, key="wrong-step")).reason == "action_outside_active_step"


def test_tenants_policy_switch_delete_and_feedback_provenance():
    harness = LiveHarness()
    first = harness.turn("alpha", DELIVERY, turn(step="callback"))
    assert harness.action("beta", DELIVERY, check()).reason == "unknown_or_expired_call"
    cross = turn("9006790001", 2, reply_to=first.question.id)
    harness.turn("alpha", DELIVERY, cross)
    event = Feedback(call_id="same-call", decision_id=first.decision_id, feedback_id="f1",
                     kind="clarification", answer_turn_id="turn-2")
    with pytest.raises(Refused, match="unknown_decision"):
        harness.feedback("beta", DELIVERY, event)
    assert harness.feedback("alpha", DELIVERY, event).source == "caller_readback"
    assert harness.feedback("alpha", DELIVERY, event).answer_turn_id == "turn-2"
    assert harness.action("alpha", DELIVERY, check(2)).outcome == "allow"
    review = Feedback(call_id="same-call", decision_id=first.decision_id, feedback_id="f2", kind="review",
                      outcome="incorrect", evidence_ref="case-4593")
    with pytest.raises(Refused, match="review_credential_required"):
        harness.feedback("alpha", DELIVERY, review)
    assert harness.feedback("alpha", DELIVERY, review, can_review=True).source == "authorized_review"
    with pytest.raises(Refused, match="policy_version_changed"):
        harness.action("alpha", DELIVERY.model_copy(update={"version": "broken"}), check(2))
    with pytest.raises(Refused, match="policy_version_changed"):
        harness.action("alpha", DELIVERY, check(2))
    harness.delete("alpha", "same-call")
    assert harness.action("alpha", DELIVERY, check(2)).reason == "unknown_or_expired_call"


def test_unknown_constraints_and_extra_arguments_go_to_review():
    policy = Policy.model_validate(DELIVERY.model_dump() | {
        "fields": DELIVERY.model_dump()["fields"] | {
            "order_id": {"type": "barcode", "question": "What is your order ID?", "cues": ["order ID"]},
        },
    })
    harness = LiveHarness()
    first = harness.turn("tenant", policy, turn(step="callback"))
    assert first.outcome == "review" and first.reason == "validator_unavailable"
    assert harness.action("tenant", policy, check()).outcome == "review"
    payload = check(arguments=ARGS | {"backdoor": "x"}, key="extra")
    assert harness.action("tenant", policy, payload).reason == "undeclared_arguments"


@pytest.mark.parametrize("spoken,expected", [("₹1,25,000.50", "INR 125000.5"), ("INR 125.125", None), (
    "USD 1200", None), ("INR 99e2", None), ("INR 1,20", None)])
def test_decimal_currency_uses_exact_parser(spoken, expected):
    assert canonical(spoken, DELIVERY.fields["collection_amount"], is_spoken=True) == expected


@pytest.mark.parametrize("value", ["+919006790001", "90067 90001", "9006790001 or 9006790002"])
def test_protected_tool_values_are_not_rewritten(value):
    harness = LiveHarness()
    first = harness.turn("tenant", DELIVERY, turn(step="callback"))
    harness.turn("tenant", DELIVERY, turn("90067 90001", n=2, reply_to=first.question.id))
    assert harness.action("tenant", DELIVERY, check(2, ARGS | {"callback_phone": value})).outcome == "review"


def test_supported_evidence_with_same_values_cannot_be_used_without_readback():
    provider = Provider(name="fixture", model="model", version="test1")
    first = turn(ORIGINAL, provider=provider, alternative_provider=provider, alternative=ORIGINAL,
                 alternative_context_free=True, step="callback")
    recorded = LiveHarness().turn("tenant", DELIVERY, first)
    assert recorded.question.field == "callback_phone"
    assert recorded.fields[0].reason == "caller_readback_required"


def test_same_runtime_applies_appointment_policy():
    harness = LiveHarness()
    text = "Booking ID BK-412; appointment date 2027-02-15; appointment time 11:05"
    recorded = harness.turn("tenant", APPOINTMENT, turn(text, step="reschedule"))
    assert recorded.question.field == "date"
    answer = harness.turn("tenant", APPOINTMENT, turn("2027-02-16", 2, reply_to=recorded.question.id))
    assert answer.outcome == "recorded"
    arguments = {"appointment_id": "BK-412", "date": "2027-02-16", "time": "11:05"}
    assert harness.action("tenant", APPOINTMENT, check(2, arguments, action="reschedule_appointment")).outcome == "allow"


def test_deadline_cannot_publish_a_late_decision(monkeypatch):
    harness = LiveHarness(clock := Clock())
    original = harness._turn_decision

    def late(*args):
        decision = original(*args)
        clock.now += 0.351
        return decision

    monkeypatch.setattr(harness, "_turn_decision", late)
    with pytest.raises(Refused, match="deadline_exceeded"):
        harness.turn("tenant", DELIVERY, turn())
    assert harness.action("tenant", DELIVERY, check()).reason == "unknown_or_expired_call"


def test_expired_evidence_revokes_same_idempotent_allow():
    harness = LiveHarness(clock := Clock())
    original = harness.turn("tenant", DELIVERY, turn(step="callback"))
    harness.turn("tenant", DELIVERY, turn("9006790001", 2, reply_to=original.question.id))
    payload = check(2)
    assert harness.action("tenant", DELIVERY, payload).outcome == "allow"
    clock.now += DELIVERY.evidence_seconds
    assert harness.action("tenant", DELIVERY, payload).reason == "authorization_expired"


def test_quoted_cancellation_and_multiple_actions_do_not_authorize():
    harness = LiveHarness()
    prior = harness.turn("tenant", DELIVERY, turn(ORIGINAL + "; do not change it", step="callback"))
    assert prior.outcome in ("ask", "review")
    assert all(field.status != "supported" for field in prior.fields)
    harness.turn("tenant", DELIVERY, turn("Try again?", 2, reply_to="wrong-question"))
    assert harness.action("tenant", DELIVERY, check(2, key="wrong")).outcome == "review"


def test_clause_and_optional_arguments_keep_inr_grouping():
    harness = LiveHarness()
    policy = Policy.model_validate(DELIVERY.model_dump() | {"actions": {
        "update_collection_amount": {"required": ["collection_amount", "order_id"], "optional": ["postal_code"]},
    }, "steps": {"payment": "update_collection_amount"}})
    transcript = "Order ID I-728, and collection amount ₹1,25,000.50"
    first = harness.turn("tenant", policy, turn(transcript, step="payment"))
    assert first.question.field == "collection_amount"
    span = first.fields[0].spans[0]
    assert transcript[span.start:span.end] == "₹1,25,000.50"
    answer = turn("INR 1,25,000.50", 2, reply_to=first.question.id)
    harness.turn("tenant", policy, answer)
    exact = {"collection_amount": "INR 125000.50", "order_id": "I-728"}
    with_extra = check(2, exact | {"postal_code": "520083"}, "optional", action="update_collection_amount")
    assert harness.action("tenant", policy, with_extra).outcome == "review"
    assert harness.action("tenant", policy, check(2, exact, action="update_collection_amount")).outcome == "allow"


def test_failed_optional_clarification_cannot_be_bypassed_by_omitting_argument():
    harness = LiveHarness()
    policy = Policy.model_validate(DELIVERY.model_dump() | {"actions": {
        "update_callback": {"required": ["order_id"], "optional": ["callback_phone"]},
    }, "steps": {"callback": "update_callback"}})
    harness.turn("tenant", policy, turn(step="callback"))
    ask = harness.action("tenant", policy, check())
    harness.turn("tenant", policy, turn("yes", 2, reply_to=ask.question.id))
    omitted = check(2, {"order_id": "I-728"}, "omit-disputed-field")
    assert harness.action("tenant", policy, omitted).reason == "readback_unavailable"
