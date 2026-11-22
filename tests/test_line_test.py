"""One recording on its clear copy and a worse line (D-057). No test here reaches a paid model."""
from __future__ import annotations

import base64
import io
import subprocess
import wave

import pytest

from app import v1, v1_line
from pehchaan.config import settings
from pehchaan_sdk import VerifyResult
from tests.v1_support import CONTEXT, GOOD, TEXT, WAV

LINES = settings()["api"]["line_test"]["lines"]


def post(client, content=WAV, name="call.wav", headers=GOOD, **fields):
    return client.post("/v1/line-test", headers=headers, files={"audio": (name, content, "audio/wav")}, data=fields)


def verified(client, text, alt=None) -> VerifyResult:
    body = {"text": text, "context": CONTEXT, "alt_text": alt}
    return VerifyResult.model_validate(client.post("/v1/verify-transcript", headers=GOOD, json=body).json())


def test_needs_a_credential_and_spends_nothing_without_one(http, fake):
    assert post(http, headers={}).status_code == 401
    assert not fake.calls


@pytest.mark.parametrize("line", ["clean", "phone", "../x", "test_real_phone", ""])
def test_only_the_configured_lines_run(http, fake, line):
    assert post(http, line=line or " ").status_code == 400
    assert not fake.calls


@pytest.mark.parametrize(
    "name,content,status",
    [("call.exe", WAV, 400), ("call.wav", b"", 400), ("call.wav", b"not audio at all", 400)],
)
def test_bad_audio_costs_nothing(http, fake, name, content, status):
    assert post(http, content=content, name=name).status_code == status
    assert not fake.calls


def test_too_long_audio_costs_nothing(http, fake):
    from app.segmenter import to_wav

    assert post(http, content=to_wav(b"\x10\x20" * 16000 * 31, 16000)).status_code == 413
    assert not fake.calls


@pytest.mark.parametrize("line", LINES)
def test_every_line_returns_real_noisy_audio_and_runs_both_copies(http, fake, line):
    reply = post(http, line=line, context='{"user": {"city": "Hyderabad"}}')
    assert reply.status_code == 200
    answer = reply.json()
    assert answer["line"] == line
    assert answer["clear"]["verified_text"] and answer["noisy"]["verified_text"]
    audio = base64.b64decode(answer["noisy_audio"].split(",", 1)[1])
    assert audio != WAV
    with wave.open(io.BytesIO(audio)) as file:
        assert (file.getframerate(), file.getnchannels(), file.getsampwidth()) == (8000, 1, 2)
        assert file.getnframes() > 0
    assert len(fake.calls) == 4  # two copies, each with its main and second-opinion transcript


@pytest.mark.parametrize("line", LINES)
def test_the_noise_is_the_benchmark_profile(http, fake, monkeypatch, line):
    seen = {}
    real = v1_line.degrade

    def spy(src, dst, *, timeout=None, **changes):
        seen.update(changes)
        real(src, dst, timeout=timeout, **changes)

    monkeypatch.setattr(v1_line, "degrade", spy)
    assert post(http, line=line).status_code == 200
    assert seen == settings()["real_check"]["conditions"][line]


def test_the_same_transcript_on_both_copies_scores_every_fact_right(http, fake):
    answer = post(http, context='{"contacts": [{"name": "Ravi Kumar", "number": "9848012345"}]}').json()
    assert answer["facts"]
    assert {f["alone"] for f in answer["facts"]} == {"right"}
    assert answer["noisy_score"]["pehchaan"]["silent"] == 0


def test_a_wrong_digit_is_silent_for_speech_alone_and_asked_with_pehchaan(http, fake):
    reference = verified(http, TEXT)
    misheard = TEXT.replace("9848012345", "9848012346")
    answer = verified(http, misheard, alt=TEXT.replace("9848012345", "9848012399"))
    side, rows = v1_line.score_against(reference, answer)
    phone = next(r for r in rows if r.type == "PHONE")
    assert phone.pehchaan == "asked"
    assert side.pehchaan.asked == 1


def test_speech_alone_is_the_no_keyword_transcript_of_the_chosen_model(http, fake):
    result = verified(http, TEXT, alt="the plain transcript")
    same = result.model_copy(deep=True)
    same.telemetry.second_opinion_model = same.telemetry.model
    other = result.model_copy(deep=True)
    other.telemetry.second_opinion_model = "another-model"
    none = result.model_copy(update={"alt_text": None}, deep=True)
    assert v1_line.speech_alone(same) == "the plain transcript"
    assert v1_line.speech_alone(other) == result.raw_text
    assert v1_line.speech_alone(none) == result.raw_text


def test_a_fact_the_clear_copy_doubted_is_not_a_reference(http, fake):
    reference = verified(http, "mera number 98480123 hai")
    assert any(f.status == "FLAGGED" for f in reference.entities)
    _, rows = v1_line.score_against(reference, reference)
    assert not rows


def test_a_fact_only_pehchaan_claims_cannot_be_a_reference(http, fake):
    clear = verified(http, TEXT)
    claimed = clear.entities[0].model_copy(update={"type": "PLACE", "value": "Zzyzx", "status": "FIXED"})
    with_claim = clear.model_copy(update={"entities": [*clear.entities, claimed]})
    assert "Zzyzx" not in [fact["value"] for fact in v1_line.reference_facts(with_claim)]


def test_a_repeated_fact_counts_once(http, fake):
    clear = verified(http, TEXT)
    doubled = clear.model_copy(update={"entities": clear.entities * 2})
    assert len(v1_line.reference_facts(doubled)) == len(v1_line.reference_facts(clear))


def test_line_tests_are_not_saved_as_calls(http, fake):
    assert post(http, context='{"user": {"id": "line-caller"}}').status_code == 200
    assert http.get("/v1/calls", params={"caller": "line-caller"}, headers=GOOD).json()["calls"] == []


def test_a_busy_server_refuses_and_frees_its_slots(http, fake, monkeypatch):
    monkeypatch.setitem(settings()["demo"], "max_active_runs", 1)
    assert post(http).status_code == 429
    assert v1._active["n"] == 0
    assert not fake.calls


def test_a_speech_outage_reports_cleanly_and_frees_its_slots(http, fake, monkeypatch):
    def down(**_):
        raise RuntimeError("upstream said sk-secret-value")

    monkeypatch.setattr(fake.audio.transcriptions, "create", down)
    reply = post(http)
    assert reply.status_code == 502
    assert "sk-secret" not in reply.text
    assert v1._active["n"] == 0


def test_a_failed_line_effect_is_a_clean_error(http, fake, monkeypatch):
    def broken(*_, **__):
        raise subprocess.CalledProcessError(1, "ffmpeg")

    monkeypatch.setattr(v1_line, "degrade", broken)
    assert post(http).status_code == 400
    assert not fake.calls


def test_a_hung_line_effect_is_a_clean_error(http, fake, monkeypatch):
    def hung(*_, **__):
        raise subprocess.TimeoutExpired("ffmpeg", 1)

    monkeypatch.setattr(v1_line, "degrade", hung)
    assert post(http).status_code == 400
    assert not fake.calls
