"""The public API: an OpenAI client works unchanged, nothing paid runs without a credential, and limits really hold."""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
import uvicorn

from app import access, v1
from app.segmenter import to_wav
from app.server import app
from pehchaan.config import settings
from tests.v1_support import CONTEXT, GOOD, TEXT, WAV


def upload(name="call.wav", content=WAV):
    return {"file": (name, content, "audio/wav")}


def test_production_wins_over_local_mode(monkeypatch):
    monkeypatch.setenv("PEHCHAAN_MODE", "local")
    monkeypatch.setenv("ENV", "production")
    assert access.is_public()


@pytest.mark.parametrize(
    "url", ["/record", "/studio", "/api/scripts", "/static/record.html", "/static/studio.html", "/static/js/studio.js"]
)
def test_private_pages_are_gone_in_production(http, url):
    assert http.get(url).status_code == 404


def test_docs_list_only_the_public_api(http):
    paths = set(http.get("/openapi.json").json()["paths"])
    assert {
        "/v1/audio/transcriptions",
        "/v1/verify-audio",
        "/v1/verify-transcript",
        "/v1/memory/confirm",
        "/v1/bench",
        "/health",
    } <= paths
    assert not [p for p in paths if p.startswith("/api") or "record" in p or "studio" in p]


@pytest.mark.parametrize(
    "url,kwargs",
    [
        ("/v1/audio/transcriptions", {"files": upload()}),
        ("/v1/verify-audio", {"files": {"audio": ("a.wav", WAV)}}),
        ("/v1/verify-transcript", {"json": {"text": TEXT}}),
        ("/v1/memory/confirm", {"json": {"user_id": "u", "heard": "a", "corrected": "b", "entity_type": "PERSON"}}),
    ],
)
def test_live_routes_need_a_credential(http, fake, url, kwargs):
    assert http.post(url, **kwargs).status_code == 401
    assert not fake.calls


def test_wrong_passcode_is_refused(http, fake):
    assert (
        http.post("/v1/verify-transcript", json={"text": TEXT}, headers={"X-Demo-Passcode": "nope"}).status_code == 401
    )


def test_free_evidence_needs_no_credential(http):
    assert http.get("/health").json()["status"] == "ok"
    assert http.get("/v1/bench").json()["exam"]["standard"]["n_clips"] == 30


def test_health_proves_the_engine_is_the_one_that_sat_the_exam(http):
    v1._engine_matches_exam.cache_clear()
    assert http.get("/health").json()["engine_matches_exam"] is True


def test_proxy_response_keeps_the_openai_shape(http, fake):
    reply = http.post(
        "/v1/audio/transcriptions",
        files=upload(),
        data={"model": "gpt-transcribe"},
        headers={**GOOD, "X-Pehchaan-Context": json.dumps(CONTEXT)},
    )
    assert reply.status_code == 200
    body = reply.json()
    assert isinstance(body["text"], str) and {"entities", "flags", "clarifier_prompt", "telemetry"} <= set(
        body["pehchaan"]
    )
    assert body["pehchaan"]["telemetry"]["evidence"] == "exam"
    assert any("Ravi Kumar" in (c.get("keywords") or []) for c in fake.calls)


def test_proxy_errors_use_the_openai_error_shape(http):
    assert http.post("/v1/audio/transcriptions", files=upload()).json()["error"]["code"] == 401
    bad = http.post("/v1/audio/transcriptions", files=upload(), data={"response_format": "srt"}, headers=GOOD)
    assert bad.status_code == 400 and "error" in bad.json()


def test_proxy_can_return_plain_text(http):
    reply = http.post("/v1/audio/transcriptions", files=upload(), data={"response_format": "text"}, headers=GOOD)
    assert reply.status_code == 200 and "9848012345" in reply.text.replace(" ", "")


def test_unknown_model_cannot_be_billed(http, fake):
    assert (
        http.post("/v1/audio/transcriptions", files=upload(), data={"model": "o3-pro"}, headers=GOOD).status_code == 400
    )
    assert not fake.calls


def test_a_callers_key_is_used_and_the_server_key_is_never_substituted(http, fake):
    key = "sk-customer-key-0123456789"
    assert (
        http.post("/v1/audio/transcriptions", files=upload(), headers={"Authorization": f"Bearer {key}"}).status_code
        == 200
    )
    assert fake.keys and set(fake.keys) == {key}


def test_real_openai_client_needs_only_base_url(fake):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", ws="none"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    try:
        from openai import OpenAI

        real = OpenAI(base_url=f"http://127.0.0.1:{port}/v1", api_key="sk-customer-key-0123456789", max_retries=0)
        answer = real.audio.transcriptions.create(model="gpt-transcribe", file=("call.wav", WAV))
        assert "9848012345" in answer.text.replace(" ", "") and answer.model_extra["pehchaan"]["telemetry"]["model"] == "gpt-transcribe"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "name,content,status",
    [
        ("call.wav", b"this is not audio", 400),
        ("call.exe", WAV, 400),
        ("call.wav", to_wav(b"\x10\x20" * 16000 * 31, 16000), 413),
        ("call.wav", b"x" * (5 * 1024 * 1024 + 2), 413),
    ],
)
def test_bad_audio_never_reaches_a_paid_model(http, fake, name, content, status):
    assert http.post("/v1/audio/transcriptions", files=upload(name, content), headers=GOOD).status_code == status
    assert not fake.calls


def test_per_ip_hourly_limit(http, monkeypatch):
    monkeypatch.setitem(settings()["api"], "per_ip_per_hour", 2)
    codes = [http.post("/v1/verify-transcript", json={"text": TEXT}, headers=GOOD).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_daily_cap_holds_and_a_callers_key_cannot_use_it_up(http, monkeypatch):
    monkeypatch.setitem(settings()["demo"], "public_live_runs_per_day", 1)
    byok = {"X-OpenAI-Key": "sk-customer-key-0123456789"}
    assert http.post("/v1/verify-transcript", json={"text": TEXT}, headers=byok).status_code == 200
    assert http.post("/v1/verify-transcript", json={"text": TEXT}, headers=GOOD).status_code == 200
    assert http.post("/v1/verify-transcript", json={"text": TEXT}, headers=GOOD).status_code == 429


def test_memory_cannot_learn_numbers_and_is_private_to_each_credential(http):
    numbers = {"user_id": "u", "heard": "9848012345", "corrected": "9848012346", "entity_type": "PHONE"}
    assert http.post("/v1/memory/confirm", json=numbers, headers=GOOD).json()["adopted"] is False
    name = {"user_id": "u", "heard": "Rajeshwaree", "corrected": "Rajeshwari", "entity_type": "PERSON"}
    assert http.post("/v1/memory/confirm", json=name, headers=GOOD).json()["adopted"] is True
    said = {"text": "Main Rajeshwaree bol rahi hoon", "context": {"user_id": "u"}}
    assert "Rajeshwari" in http.post("/v1/verify-transcript", json=said, headers=GOOD).json()["verified_text"]
    other = {"X-OpenAI-Key": "sk-customer-key-0123456789"}
    assert "Rajeshwaree" in http.post("/v1/verify-transcript", json=said, headers=other).json()["verified_text"]
