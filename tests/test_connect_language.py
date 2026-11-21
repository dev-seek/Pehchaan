"""Connecting says plainly whether a key works, and a chosen language reaches the speech model and the number guard."""

from __future__ import annotations

import importlib.util
import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from app import v1_connect
from app.server import app
from pehchaan.config import ROOT, settings
from pehchaan.resolvers import NullMemoryStore
from pehchaan_sdk import CustomTranscriptProvider, OpenAIProvider, Pehchaan
from tests.v1_support import CONTEXT, GOOD, WAV

KEY = {"X-OpenAI-Key": "sk-customer-key-000000000000"}


def _error(kind, status):
    response = httpx.Response(status, request=httpx.Request("GET", "https://api.openai.com/v1/models"))
    return kind("refused", response=response, body=None)


def test_connect_with_the_passcode_lists_every_model(http):
    answer = http.post("/v1/connect", headers=GOOD).json()
    assert answer["ok"] and answer["kind"] == "passcode"
    assert [m["id"] for m in answer["models"]] == list(settings()["sdk"]["models"])
    assert answer["limits"]["per_hour"] == settings()["api"]["per_ip_per_hour"]
    assert answer["limits"]["left_this_hour"] == settings()["api"]["per_ip_per_hour"]


def test_connect_does_not_use_up_a_live_request(http):
    http.post("/v1/connect", headers=GOOD)
    assert (
        http.post("/v1/connect", headers=GOOD).json()["limits"]["left_this_hour"]
        == settings()["api"]["per_ip_per_hour"]
    )


def test_connect_rejects_a_wrong_passcode(http):
    assert http.post("/v1/connect", headers={"X-Demo-Passcode": "wrong"}).status_code == 401


def test_connect_with_a_key_shows_only_the_models_it_can_use(http, monkeypatch):
    monkeypatch.setattr(v1_connect, "_list_models", lambda _: {"whisper-1", "gpt-4.1-mini"})
    answer = http.post("/v1/connect", headers=KEY).json()
    assert answer["kind"] == "byok" and answer["key_checked"]
    assert [m["id"] for m in answer["models"]] == ["whisper-1"]


def test_connect_reports_a_key_openai_rejects(http, monkeypatch):
    def refuse(_):
        raise _error(openai.AuthenticationError, 401)

    monkeypatch.setattr(v1_connect, "_list_models", refuse)
    response = http.post("/v1/connect", headers=KEY)
    assert response.status_code == 401 and "rejected" in response.json()["detail"]
    assert KEY["X-OpenAI-Key"] not in response.text


def test_a_restricted_key_that_cannot_list_models_can_still_connect(http, monkeypatch):
    def refuse(_):
        raise _error(openai.PermissionDeniedError, 403)

    monkeypatch.setattr(v1_connect, "_list_models", refuse)
    answer = http.post("/v1/connect", headers=KEY).json()
    assert answer["ok"] and not answer["key_checked"] and len(answer["models"]) == len(settings()["sdk"]["models"])


def test_a_key_with_no_speech_models_is_told_so(http, monkeypatch):
    monkeypatch.setattr(v1_connect, "_list_models", lambda _: {"gpt-4.1-mini"})
    assert http.post("/v1/connect", headers=KEY).status_code == 403


def test_verify_audio_passes_the_language_to_both_transcripts(http, fake):
    response = http.post(
        "/v1/verify-audio",
        headers=GOOD,
        files={"audio": ("call.wav", WAV, "audio/wav")},
        data={"language": "ta", "context": json.dumps(CONTEXT)},
    )
    assert response.status_code == 200 and response.json()["telemetry"]["evidence"] == "unmeasured"
    assert [call["languages"] for call in fake.calls] == [["ta"], ["ta"]]


@pytest.mark.parametrize("language", ["not a language", "x", "../etc"])
def test_a_malformed_language_is_refused(http, language):
    response = http.post("/v1/verify-transcript", headers=GOOD, json={"text": "hello there", "language": language})
    assert response.status_code == 400


def test_verify_transcript_uses_the_language_to_protect_money(http):
    spoken = "दोन लाख रुपये द्या"
    answer = http.post("/v1/verify-transcript", headers=GOOD, json={"text": spoken, "language": "mr"}).json()
    assert answer["verified_text"] == spoken
    assert all(f["status"] == "FLAGGED" for f in answer["entities"] if f["type"] == "AMOUNT")


def test_stream_carries_the_language(http):
    spoken = "दोन लाख रुपये द्या"
    with http.websocket_connect("/v1/stream") as ws:
        ws.send_json(
            {"type": "start", "mode": "transcript", "language": "mr", "auth": {"passcode": GOOD["X-Demo-Passcode"]}}
        )
        ws.send_json({"type": "transcript", "text": spoken, "is_final": True})
        ws.send_json({"type": "stop"})
        while (message := ws.receive_json())["type"] != "final":
            pass
    assert message["result"]["verified_text"] == spoken


def test_a_language_the_model_refuses_is_retried_without_a_hint():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        if "languages" in kwargs:
            raise _error(openai.BadRequestError, 400)
        return SimpleNamespace(text="heard")

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=create)))
    answer = OpenAIProvider("gpt-transcribe", client=client).transcribe(("x" * 4).encode(), language="pa")
    assert answer.text == "heard" and len(calls) == 2


@pytest.mark.parametrize("language,hint", [("hi-IN", ["hi"]), ("ta", ["ta"]), ("hl", ["hi", "en", "te"])])
def test_language_codes_become_what_the_speech_model_accepts(language, hint):
    assert OpenAIProvider("gpt-transcribe", client=object()).request(None, language)["languages"] == hint


def test_custom_providers_accept_a_language():
    provider = CustomTranscriptProvider(lambda _audio, _keywords: "Main Ravi bol raha hoon")
    sdk = Pehchaan(provider, judge=None, memory=NullMemoryStore())
    assert "Ravi" in sdk.verify_audio(b"audio", language="ta").verified_text


def test_published_language_table_matches_a_fresh_run(monkeypatch, tmp_path):
    monkeypatch.setattr("pehchaan_sdk.client._state_dir", lambda: tmp_path)
    spec = importlib.util.spec_from_file_location("language_probe", ROOT / "tools" / "language_probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    assert json.loads(probe.OUTPUT.read_text(encoding="utf-8")) == probe.probe()


def test_bench_publishes_the_language_table(http):
    table = http.get("/v1/bench").json()["languages"]["languages"]
    tiers = {row["code"]: row["tier"] for row in table}
    assert (
        tiers["hi"] == "measured"
        and tiers["te"] == "built"
        and tiers["ta"] == "partial"
        and tiers["ur"] == "unsupported"
    )
    assert all(row["facts"]["money_wrong"] == 0 for row in table)
    assert app is not None
