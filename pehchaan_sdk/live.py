"""Async client for finalized turns, tool checks and feedback under API v2."""

from __future__ import annotations

import asyncio
from time import monotonic

import httpx
from pydantic import TypeAdapter

from pehchaan_live.contracts import Action, Decision, Feedback, FeedbackReceipt, Identifier, Turn
from pehchaan_live.settings import live_settings


class LiveUnavailable(RuntimeError):
    """The integration must defer this tool invocation."""


class LiveClient:
    def __init__(self, base_url: str, token: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self.deadline = live_settings()["runtime"]["deadline_ms"] / 1000
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.deadline,
            transport=transport,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _send(self, route, payload, schema):
        started = monotonic()
        try:
            response = await asyncio.wait_for(
                self._client.post(route, json=payload.model_dump(mode="json")),
                self.deadline,
            )
            response.raise_for_status()
            result = schema.model_validate_json(response.content)
        except (asyncio.TimeoutError, httpx.HTTPError, ValueError) as exc:
            raise LiveUnavailable("live_check_unavailable") from exc
        if monotonic() - started >= self.deadline:
            raise LiveUnavailable("live_check_deadline_exceeded")
        return result

    async def turn(self, payload: Turn) -> Decision:
        response = await self._send("v2/turns", payload, Decision)
        if (response.call_id, response.turn_id) != (payload.call_id, payload.turn_id):
            raise LiveUnavailable("turn_receipt_mismatch")
        return response

    async def check(self, payload: Action) -> Decision:
        response = await self._send("v2/actions/check", payload, Decision)
        if (response.call_id, response.turn_id, response.action) != (payload.call_id, payload.turn_id, payload.action):
            raise LiveUnavailable("action_receipt_mismatch")
        return response

    async def feedback(self, payload: Feedback) -> FeedbackReceipt:
        response = await self._send("v2/feedback", payload, FeedbackReceipt)
        if (response.decision_id, response.feedback_id) != (payload.decision_id, payload.feedback_id):
            raise LiveUnavailable("feedback_receipt_mismatch")
        return response

    async def delete_call(self, call_id: str) -> None:
        call_id = TypeAdapter(Identifier).validate_python(call_id)
        try:
            response = await asyncio.wait_for(self._client.delete(f"v2/calls/{call_id}"), self.deadline)
            response.raise_for_status()
        except (asyncio.TimeoutError, httpx.HTTPError) as exc:
            raise LiveUnavailable("live_cleanup_unavailable") from exc
