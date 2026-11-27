"""Reference platform-owned gateway for one call and its tool execution boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic
from uuid import uuid4

from pehchaan_live.contracts import Action, Decision, Feedback, Provider, Question, Turn
from pehchaan_sdk.live import LiveClient, LiveUnavailable


@dataclass(frozen=True)
class ToolResult:
    outcome: str
    reason: str
    decision: Decision | None = None


class CallGate:
    def __init__(self, client: LiveClient, *, call_id: str | None = None, step: str | None = None):
        self.client = client
        self.call_id = call_id or uuid4().hex
        self.step = step
        self._sequence = 0
        self._turn: Decision | None = None
        self._pending: Decision | None = None
        self._spoken: str | None = None
        self._written: set[str] = set()
        self._generation = 0
        self._turn_seconds = 0.0
        self._feedback_tasks: set[asyncio.Task] = set()
        self._submission_lock = asyncio.Lock()

    def block(self) -> None:
        # Run before awaiting ingestion, so a tool check already in flight cannot authorize a write.
        self._generation += 1
        self._turn = None

    @property
    def question(self) -> Question | None:
        return self._pending.question if self._pending else None

    def question_played(self, question_id: str) -> None:
        if self.question and self.question.id == question_id:
            self._spoken = question_id

    def _remember_question(self, result: Decision) -> None:
        if result.question and (not self.question or self.question.id != result.question.id):
            self._pending = result
            self._spoken = None

    async def _feedback(self, event: Feedback) -> None:
        try:
            await self.client.feedback(event)
        except LiveUnavailable:
            pass  # Feedback is observational. The bound answer has already been checked.

    async def finalized(self, transcript: str, *, provider: Provider | None = None, interrupted: bool = False):
        started = monotonic()
        pending = self._pending
        self.block()
        generation = self._generation
        async with self._submission_lock:
            self._sequence += 1
            reply_to = pending.question.id if pending and pending.question.id == self._spoken else None
            if pending and not reply_to:
                interrupted = True
            self._pending = None
            self._spoken = None
            turn = Turn(
                call_id=self.call_id,
                turn_id=uuid4().hex,
                sequence=self._sequence,
                transcript=transcript,
                status="interrupted" if interrupted else "finalized",
                provider=provider,
                step=self.step,
                reply_to=reply_to,
            )
            try:
                result = await self.client.turn(turn)
            except LiveUnavailable:
                # A lost response leaves the remote sequence uncertain. Future writes stay gated.
                return None
            if self._generation != generation:
                return None
            self._turn = result
            self._turn_seconds = monotonic() - started
            self._remember_question(result)
            if reply_to and any(field.reason == "caller_readback" for field in result.fields):
                event = Feedback(
                    call_id=self.call_id,
                    decision_id=pending.decision_id,
                    feedback_id=uuid4().hex,
                    kind="clarification",
                    answer_turn_id=turn.turn_id,
                )
                task = asyncio.create_task(self._feedback(event))
                self._feedback_tasks.add(task)
                task.add_done_callback(self._feedback_tasks.discard)
            return result

    async def execute(
        self,
        action: str,
        arguments: dict[str, str],
        *,
        operation_id: str,
        write: Callable[[dict[str, str], str], Awaitable[None]],
    ) -> ToolResult:
        turn, generation = self._turn, self._generation
        if turn is None or turn.outcome not in {"recorded", "ask"}:
            return ToolResult("review", "no_current_finalized_turn")
        if operation_id in self._written:
            return ToolResult("review", "write_already_attempted")
        invocation = json.dumps([operation_id, turn.turn_id, arguments], sort_keys=True, separators=(",", ":"))
        payload = Action(
            call_id=self.call_id,
            turn_id=turn.turn_id,
            action=action,
            arguments=dict(arguments),
            idempotency_key=hashlib.sha256(invocation.encode()).hexdigest(),
        )
        remaining = self.client.deadline - self._turn_seconds
        if remaining <= 0:
            return ToolResult("review", "harness_deadline_exceeded")
        try:
            result = await asyncio.wait_for(self.client.check(payload), timeout=remaining)
        except (asyncio.TimeoutError, LiveUnavailable):
            return ToolResult("review", "harness_unavailable")
        if self._generation != generation or operation_id in self._written:
            return ToolResult("review", "turn_changed_or_write_already_attempted")
        if (result.policy_id, result.policy_version) != (turn.policy_id, turn.policy_version):
            return ToolResult("review", "policy_changed")
        self._remember_question(result)
        if result.outcome == "allow":
            self._written.add(operation_id)
            # The customer tool owns the actual write and must also enforce its own idempotency key.
            await write(dict(payload.arguments), self.call_id + ":" + operation_id)
        return ToolResult(result.outcome, result.reason, result)

    async def close(self) -> None:
        self.block()
        self._pending = None
        if self._feedback_tasks:
            await asyncio.gather(*self._feedback_tasks)
        try:
            await self.client.delete_call(self.call_id)
        except LiveUnavailable:
            pass  # Active state expires on the service.
