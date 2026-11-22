"""Running with no API key (D-058): a labelled stand-in for speech that a production server can never use."""
from __future__ import annotations

from pathlib import Path

import pytest

from app import access
from app.mock_speech import MODEL, MockSpeech, mock_speech_on
from pehchaan.config import ROOT
from pehchaan_sdk import AudioFile
from tests.v1_support import GOOD, WAV


@pytest.fixture
def no_key(fake, monkeypatch):
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("PEHCHAAN_MODE", "public")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PEHCHAAN_MOCK_SPEECH", "1")
    access._windows.clear()
    return fake


def test_it_is_on_only_when_asked_with_no_key_and_off_production(no_key, monkeypatch):
    assert mock_speech_on()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-a-real-key-would-go-here")
    assert not mock_speech_on()
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("ENV", "production")
    assert not mock_speech_on()
    monkeypatch.delenv("ENV")
    monkeypatch.setenv("PEHCHAAN_MOCK_SPEECH", "0")
    assert not mock_speech_on()


def test_production_with_the_flag_still_needs_a_real_key(http, fake, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("PEHCHAAN_MOCK_SPEECH", "1")
    reply = http.post("/v1/verify-audio", headers=GOOD, files={"audio": ("a.wav", WAV, "audio/wav")})
    assert reply.status_code == 503


def test_connect_lists_only_the_mock(http, no_key):
    answer = http.post("/v1/connect", headers=GOOD).json()
    assert [model["id"] for model in answer["models"]] == [MODEL]
    assert answer["models"][0]["evidence"] == "unmeasured"


def test_audio_runs_end_to_end_labelled_as_mock_and_calls_nothing_paid(http, no_key):
    context = '{"contacts": [{"name": "Ravi Kumar", "number": "9848012345"}]}'
    fields = {"model": MODEL, "context": context}
    reply = http.post("/v1/verify-audio", headers=GOOD, files={"audio": ("a.wav", WAV, "audio/wav")}, data=fields)
    assert reply.status_code == 200
    answer = reply.json()
    assert answer["telemetry"]["model"] == MODEL
    assert answer["telemetry"]["evidence"] == "unmeasured"
    assert "Ravi Kumar" in answer["verified_text"]
    assert not no_key.calls


def test_a_real_key_from_the_visitor_replaces_the_mock(http, no_key):
    headers = {"X-OpenAI-Key": "sk-visitor-key-long-enough-1234"}
    reply = http.post("/v1/verify-audio", headers=headers, files={"audio": ("a.wav", WAV, "audio/wav")})
    assert reply.status_code == 200
    assert reply.json()["telemetry"]["model"] != MODEL
    assert no_key.calls


def test_the_noisy_line_says_it_needs_real_speech(http, no_key):
    reply = http.post("/v1/line-test", headers=GOOD, files={"audio": ("a.wav", WAV, "audio/wav")}, data={"model": MODEL})
    assert reply.status_code == 503
    assert "real speech model" in reply.json()["detail"]


def test_live_phrases_arrive_in_order_and_do_not_repeat():
    speech = MockSpeech()
    said = [speech.transcribe(AudioFile("phrase.wav", WAV)).text for _ in range(5)]
    assert len(set(said[:3])) == 3
    assert " ".join(said[:3]) == MockSpeech().transcribe(AudioFile("call.wav", WAV)).text
    assert said[3] == said[4]


def test_the_example_env_file_cannot_pretend_to_be_a_key():
    lines = Path(ROOT / ".env.example").read_text().splitlines()
    assert "OPENAI_API_KEY=" in lines
