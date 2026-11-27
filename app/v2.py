"""HTTP transport and deadline enforcement for the action-checking API."""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, suppress
from threading import BoundedSemaphore
from time import monotonic

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.security import HTTPBearer

from pehchaan_live.contracts import Action, Decision, Feedback, FeedbackReceipt, Identifier, Turn
from pehchaan_live.runtime import LiveHarness, Refused
from pehchaan_live.settings import live_settings

from .v2_access import Credential, authenticate

runtime = LiveHarness()
config = live_settings()["runtime"]
workers = ThreadPoolExecutor(max_workers=config["worker_count"], thread_name_prefix="pehchaan-live")
capacity = BoundedSemaphore(config["worker_count"])
audit = logging.getLogger("pehchaan.live.audit")


async def _reap_sessions() -> None:
    while True:
        await asyncio.sleep(min(60, config["session_seconds"] / 10))
        await asyncio.to_thread(runtime.purge_expired)


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(_reap_sessions())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


class GuardedRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def guarded(request: Request):
            clock = monotonic()
            request.state.deadline = clock + config["deadline_ms"] / 1000
            request.state.credential = authenticate(request)
            size = 0

            async def limited_receive():
                nonlocal size
                message = await request.receive()
                size += len(message.get("body", b""))
                if size > config["max_request_bytes"]:
                    raise HTTPException(413, "request_too_large")
                return message

            try:
                remaining = request.state.deadline - monotonic()
                if remaining <= 0:
                    raise HTTPException(503, "deadline_exceeded")
                response = await asyncio.wait_for(handle(Request(request.scope, limited_receive)), remaining)
                if monotonic() >= request.state.deadline:
                    raise HTTPException(503, "deadline_exceeded")
            except asyncio.TimeoutError as exc:
                raise HTTPException(503, "deadline_exceeded") from exc
            except RequestValidationError as exc:
                # Validation details from Pydantic can contain raw transcripts or tool arguments.
                raise HTTPException(422, "invalid_request") from exc
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Pehchaan-Latency-Ms"] = f"{(monotonic() - clock) * 1000:.3f}"
            return response

        return guarded


router = APIRouter(prefix="/v2", tags=["Live action checks"], route_class=GuardedRoute,
                   dependencies=[Depends(HTTPBearer(auto_error=False))])


def _dispatch(auth: Credential, method, payload, deadline: float, kwargs: dict):
    if method == runtime.delete:
        return method(auth.tenant, payload, deadline=deadline)
    try:
        policy = auth.policy_for(payload.call_id)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as exc:
        raise Refused("invalid_platform_configuration", 503) from exc
    return method(auth.tenant, policy, payload, deadline=deadline, **kwargs)


def _audit(credential: Credential, result, operation: str) -> None:
    if not audit.isEnabledFor(logging.INFO):
        return
    event = {"tenant": credential.tenant, "operation": operation}
    if isinstance(result, Decision):
        event.update(decision_id=result.decision_id, policy_id=result.policy_id, policy_version=result.policy_version,
                     outcome=result.outcome, reason=result.reason, latency_ms=result.latency_ms)
    elif isinstance(result, FeedbackReceipt):
        event.update(decision_id=result.decision_id, source=result.source, outcome=result.outcome)
    audit.info("%s", json.dumps(event, separators=(",", ":")))


async def _run(request: Request, method, payload, **kwargs):
    auth = request.state.credential
    if not capacity.acquire(blocking=False):
        raise HTTPException(503, "harness_busy")
    try:
        job = workers.submit(_dispatch, auth, method, payload, request.state.deadline, kwargs)
    except BaseException:
        capacity.release()
        raise
    job.add_done_callback(lambda _: capacity.release())
    try:
        result = await asyncio.wrap_future(job)
        _audit(auth, result, method.__name__)
        return result
    except Refused as exc:
        detail = str(exc)
        raise HTTPException(exc.status, detail) from exc


@router.post("/turns", response_model=Decision)
async def submit_turn(request: Request, turn: Turn):
    if request.state.credential.can_review:
        raise HTTPException(403, "gateway_credential_required")
    return await _run(request, runtime.turn, turn)


@router.post("/actions/check", response_model=Decision)
async def check_action(request: Request, action: Action):
    if request.state.credential.can_review:
        raise HTTPException(403, "gateway_credential_required")
    return await _run(request, runtime.action, action)


@router.post("/feedback", response_model=FeedbackReceipt)
async def record_feedback(request: Request, event: Feedback):
    return await _run(request, runtime.feedback, event, can_review=request.state.credential.can_review)


@router.delete("/calls/{call_id}", status_code=204)
async def delete_call(request: Request, call_id: Identifier):
    if request.state.credential.can_review:
        raise HTTPException(403, "gateway_credential_required")
    await _run(request, runtime.delete, call_id)
    return Response(status_code=204)
