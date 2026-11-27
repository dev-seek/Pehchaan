"""Run the HTTP API and customer tool boundary without provider credentials."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.server import app
from integrations.call_gate import CallGate
from pehchaan_sdk import LiveClient

TOKEN = "local-gateway-example-25chars"
REVIEW = "local-reviewer-example-25chars"
CALL = {"call_id": "local-call", "turn_id": "t1", "sequence": 1,
        "transcript": "Order ID PA-321; callback number 9001470010", "step": "callback"}
ARGS = {"order_id": "PA-321", "callback_phone": "9001470010"}


@pytest.fixture
def gateway(monkeypatch):
    from app.v2 import runtime
    from app.v2_access import _window

    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("PEHCHAAN_V2_TENANTS", raising=False)
    monkeypatch.setenv("PEHCHAAN_V2_TOKEN", TOKEN)
    monkeypatch.setenv("PEHCHAAN_V2_REVIEW_TOKEN", REVIEW)
    monkeypatch.setenv("PEHCHAAN_V2_POLICY", "delivery")
    monkeypatch.setattr(runtime, "_sessions", {})
    _window.clear()
    return {"Authorization": f"Bearer {TOKEN}"}


def test_routes_auth_validation_feedback_and_delete(gateway):
    client = TestClient(app)
    assert client.post("/v2/turns", json=CALL).status_code == 401
    assert client.post("/v2/turns", json=CALL, headers={"X-Demo-Passcode": "review-demo"}).status_code == 401
    malformed = client.post("/v2/turns", headers=gateway, json=CALL | {"sequence": "1"})
    assert malformed.status_code == 422 and CALL["transcript"] not in malformed.text
    first = client.post("/v2/turns", headers=gateway, json=CALL)
    assert first.status_code == 200 and first.headers["Cache-Control"] == "no-store"
    assert float(first.headers["X-Pehchaan-Latency-Ms"]) >= 0
    first = first.json()
    assert first["outcome"] == "ask"
    answer = CALL | {"turn_id": "t2", "sequence": 2, "transcript": "9001470010", "reply_to": first["question"]["id"]}
    assert client.post("/v2/turns", headers=gateway, json=answer).json()["outcome"] == "recorded"
    payload = {"call_id": "local-call", "turn_id": "t2", "action": "update_callback", "arguments": ARGS,
               "idempotency_key": "operation"}
    check = client.post("/v2/actions/check", headers=gateway, json=payload).json()
    assert check["outcome"] == "allow"
    event = {"call_id": "local-call", "decision_id": check["decision_id"], "feedback_id": "ev-1",
             "kind": "outcome", "outcome": "correct", "evidence_ref": "verified-audit-01"}
    assert client.post("/v2/feedback", headers=gateway, json=event).status_code == 403
    reviewer = {"Authorization": f"Bearer {REVIEW}"}
    assert client.post("/v2/feedback", headers=reviewer, json=event).json()["source"] == "checked_outcome"
    assert client.post("/v2/turns", headers=reviewer, json=CALL).status_code == 403
    assert client.delete("/v2/calls/local-call", headers=gateway).status_code == 204
    assert client.post("/v2/actions/check", headers=gateway, json=payload).json()["outcome"] == "review"


def test_bounded_request_body_and_deadline(gateway, monkeypatch):
    from app.v2 import runtime

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
            async def large():
                yield b" " * 20000
                yield b" " * 20000
            response = await client.post("/v2/turns", headers=gateway, content=large())
            assert response.status_code == 413

            started = asyncio.Event()
            loop = asyncio.get_running_loop()
            original = runtime._turn_decision

            def slow(*args):
                from time import sleep

                loop.call_soon_threadsafe(started.set)
                sleep(0.4)
                return original(*args)
            monkeypatch.setattr(runtime, "_turn_decision", slow)
            request = asyncio.create_task(client.post("/v2/turns", headers=gateway, json=CALL))
            await asyncio.wait_for(started.wait(), 0.5)
            assert (await request).status_code == 503
            assert runtime._sessions == {}

    asyncio.run(scenario())


def test_tool_gate_keeps_exact_arguments_and_deduplicates_concurrent_writes(gateway):
    async def scenario():
        async with LiveClient("http://local", TOKEN, transport=httpx.ASGITransport(app=app)) as client:
            gate = CallGate(client, step="callback")
            original = await gate.finalized(CALL["transcript"])
            gate.question_played(original.question.id)
            await gate.finalized("9001470011")
            writes = []

            async def write(args, key):
                writes.append((args, key))
                await asyncio.sleep(0)

            async def submit(phone):
                return await gate.execute("update_callback", ARGS | {"callback_phone": phone},
                                          operation_id="same-logical-write", write=write)
            assert (await submit("9001470010")).outcome == "review"
            result = await asyncio.gather(submit("9001470011"), submit("9001470011"))
            assert sorted(item.outcome for item in result) == ["allow", "review"]
            assert writes == [(ARGS | {"callback_phone": "9001470011"}, f"{gate.call_id}:same-logical-write")]
            await gate.close()

    asyncio.run(scenario())


def test_interruption_blocks_inflight_tool_allow(gateway):
    async def scenario():
        requested = asyncio.Event()
        release = asyncio.Event()
        asgi = httpx.ASGITransport(app=app)

        async def transport(request):
            response = await asgi.handle_async_request(request)
            if request.url.path.endswith("/check"):
                requested.set()
                await release.wait()
            return response

        async with LiveClient("http://local", TOKEN, transport=httpx.MockTransport(transport)) as client:
            gate = CallGate(client, step="callback")
            result = await gate.finalized(CALL["transcript"])
            gate.question_played(result.question.id)
            await gate.finalized(ARGS["callback_phone"])

            async def write(*_args):
                pytest.fail("stale action reached the writer")

            attempt = asyncio.create_task(gate.execute("update_callback", ARGS, operation_id="first", write=write))
            await asyncio.wait_for(requested.wait(), 1)
            gate.block()
            release.set()
            assert (await attempt).outcome == "review"

    asyncio.run(scenario())


def test_interrupting_question_playout_defers_write(gateway):
    async def scenario():
        async with LiveClient("http://local", TOKEN, transport=httpx.ASGITransport(app=app)) as client:
            gate = CallGate(client, step="callback")
            assert (await gate.finalized(CALL["transcript"])).outcome == "ask"
            assert (await gate.finalized(ARGS["callback_phone"])).reason == "turn_interrupted"

    asyncio.run(scenario())


def test_configured_tenants_cannot_share_turns(gateway, monkeypatch, tmp_path):
    from pehchaan_live.policy import POLICY_DIR

    path = tmp_path / "tenants.json"
    path.write_text(json.dumps([
        {"id": "alpha", "policy": str(POLICY_DIR / "delivery.yaml"), "token_env": "PEHCHAAN_V2_TOKEN"},
        {"id": "beta", "policy": str(POLICY_DIR / "delivery.yaml"), "token_env": "PEHCHAAN_V2_REVIEW_TOKEN"},
    ]))
    monkeypatch.setenv("PEHCHAAN_V2_TENANTS", str(path))
    client = TestClient(app)
    assert client.post("/v2/turns", headers=gateway, json=CALL).json()["outcome"] == "ask"
    action = {"call_id": CALL["call_id"], "turn_id": "t1", "action": "update_callback",
              "arguments": ARGS, "idempotency_key": "check"}
    isolation = client.post("/v2/actions/check", headers={"Authorization": f"Bearer {REVIEW}"}, json=action)
    assert isolation.json()["reason"] == "unknown_or_expired_call"


def test_canary_rollback_invalidates_the_previously_allowed_http_check(gateway, monkeypatch, tmp_path):
    import yaml

    from pehchaan_live.policy import reference_policy
    from pehchaan_live.rollout import Revision, Rollout, selected_policy
    from pehchaan_live.runtime import digest

    stable = reference_policy("delivery")
    candidate = stable.model_copy(update={"version": "2.0.0"})
    for name, policy in (("active", stable), ("candidate", candidate)):
        (tmp_path / f"{name}.yaml").write_text(yaml.safe_dump(policy.model_dump()))
    approved = Revision(path="active.yaml", sha256=digest(stable))
    next_version = Revision(path="candidate.yaml", sha256=digest(candidate))
    pointer = tmp_path / "release.json"
    canary = Rollout(tenant="partner", approved=approved, candidate=next_version, phase="canary", canary_percent=70,
                     approval_ref="authorized-review", evidence_sha256="pinned-test-evidence")
    pointer.write_text(canary.model_dump_json())
    config = tmp_path / "tenants.json"
    config.write_text(json.dumps([{"id": "partner", "rollout": pointer.name, "token_env": "PEHCHAAN_V2_TOKEN"}]))
    monkeypatch.setenv("PEHCHAAN_V2_TENANTS", str(config))
    call_id = next(f"test-{i}" for i in range(100)
                   if selected_policy(pointer, "partner", f"test-{i}").version == candidate.version)
    client = TestClient(app)
    first = client.post("/v2/turns", headers=gateway, json=CALL | {"call_id": call_id}).json()
    assert first["policy_version"] == candidate.version
    answer = CALL | {"call_id": call_id, "turn_id": "t2", "sequence": 2, "transcript": ARGS["callback_phone"],
                     "reply_to": first["question"]["id"]}
    assert client.post("/v2/turns", headers=gateway, json=answer).json()["outcome"] == "recorded"
    payload = {"call_id": call_id, "turn_id": "t2", "action": "update_callback", "arguments": ARGS,
               "idempotency_key": "check"}
    assert client.post("/v2/actions/check", headers=gateway, json=payload).json()["outcome"] == "allow"
    pointer.write_text(Rollout(tenant="partner", approved=approved, phase="paused").model_dump_json())
    denied = client.post("/v2/actions/check", headers=gateway, json=payload)
    assert denied.status_code == 409 and denied.json()["detail"] == "policy_version_changed"
    pointer.write_text(canary.model_dump_json())
    assert client.post("/v2/actions/check", headers=gateway, json=payload).status_code == 409
