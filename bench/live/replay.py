"""Replay a tool opportunity without using the expected arguments to make decisions."""

from dataclasses import dataclass
from time import perf_counter

from pehchaan_live.contracts import Action, Decision
from pehchaan_live.policy import Policy
from pehchaan_live.runtime import LiveHarness

from .dataset import Opportunity, finalized


@dataclass(frozen=True)
class Outcome:
    arguments: dict[str, str] | None = None
    questions: int = 0
    latency_ms: tuple[float, ...] = ()
    fields: frozenset[str] = frozenset()
    cost_usd: float | None = 0.0
    authorized_input: dict[str, str] | None = None


def _propose(row: Opportunity, turn_id: str, arguments: dict[str, str], key: str) -> Action:
    return Action(call_id=row.id, turn_id=turn_id, action=row.action, arguments=arguments, idempotency_key=key)


def replay(row: Opportunity, policy: Policy) -> Outcome:
    harness = LiveHarness()
    times = []
    offered = row.proposed
    started = perf_counter()
    if row.early:
        result = harness.action("eval", policy, _propose(row, "turn-0", offered, "early"))
        times.append((perf_counter() - started) * 1000)
        return _outcome(offered, result, 0, times)
    turn = finalized(row)
    recorded = harness.turn("eval", policy, turn)
    if row.correction is not None:
        times.append((perf_counter() - started) * 1000)
        started = perf_counter()
        turn = finalized(row, transcript=row.correction, sequence=2)
        recorded = harness.turn("eval", policy, turn)
    result = harness.action("eval", policy, _propose(row, turn.turn_id, offered, "first-check"))
    times.append((perf_counter() - started) * 1000)
    question = result.question or recorded.question
    if question and row.reply is not None:
        started = perf_counter()
        answer = finalized(row, transcript=row.reply, sequence=turn.sequence + 1).model_copy(
            update={"reply_to": question.id, "status": row.reply_status},
        )
        harness.turn("eval", policy, answer)
        offered = row.retry_arguments if row.retry_arguments is not None else row.proposed
        result = harness.action("eval", policy, _propose(row, answer.turn_id, offered, "answer-check"))
        times.append((perf_counter() - started) * 1000)
    return _outcome(offered, result, int(question is not None), times)


def _outcome(offered: dict, result: Decision, questions: int, times: list[float]) -> Outcome:
    return Outcome(
        arguments=offered if result.outcome == "allow" else None, questions=questions, latency_ms=tuple(times),
        fields=frozenset(field.field for field in result.fields if field.status == "supported"),
        authorized_input=offered if result.outcome == "allow" else None,
    )


def raw(row: Opportunity) -> Outcome:
    return Outcome(arguments=row.proposed, fields=frozenset(row.proposed), authorized_input=row.proposed)


def native(row: Opportunity) -> Outcome:
    """Replay the independently declared reference readback/validation disposition."""
    arguments = row.native_arguments
    return Outcome(arguments=arguments, questions=int(row.reply is not None and not row.early),
                   fields=frozenset(arguments or {}), authorized_input=arguments)
