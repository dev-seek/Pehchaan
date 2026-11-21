"""The SDK must feed the frozen engine exactly as the measured system does, and must not overstate what was measured."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pehchaan import CallContext, build_pipeline
from pehchaan.asr import transcriber
from pehchaan.config import ROOT, settings
from pehchaan.judge import verifier
from pehchaan.resolvers import JsonMemoryStore
from pehchaan_sdk import ASRResult, CustomTranscriptProvider, OpenAIProvider, Pehchaan, STTProvider
from pehchaan_sdk.judge import KeyedJudge


class FakeClient:
    def __init__(self, text="hello", judge_choice="keep"):
        self.calls, self.chats = [], []
        self.text, self.judge_choice = text, judge_choice
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._transcribe))
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._complete))

    def _transcribe(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text, model_dump=lambda: {"text": self.text})

    def _complete(self, **kwargs):
        self.chats.append(kwargs)
        content = json.dumps({"choice": self.judge_choice, "reason": "fake"})
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def client(tmp_path):
    def make(provider=None, **kwargs):
        return Pehchaan(
            provider or CustomTranscriptProvider(),
            memory=JsonMemoryStore(tmp_path / "memory"),
            ledger=tmp_path / "ledger.sqlite3",
            **kwargs,
        )

    return make


def corpus():
    rows = (ROOT / settings()["learning"]["corpus"]).read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in rows if x.strip()]


def test_openai_adapter_sends_the_engine_request(monkeypatch, tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    engine = FakeClient()
    monkeypatch.setattr(transcriber, "client", lambda: engine)
    for model in settings()["sdk"]["models"]:
        keywords = ["Kondapur"] if settings()["sdk"]["models"][model]["keywords"] else None
        transcriber.transcribe(
            audio,
            model,
            keywords=keywords,
            languages=settings()["asr"]["languages"],
            timeout=settings()["asr"]["timeout_s"],
            cache_answers=False,
        )
        adapter = FakeClient()
        OpenAIProvider(model, client=adapter).transcribe(audio, keywords)
        want = {k: v for k, v in engine.calls[-1].items() if k != "file"}
        assert {k: v for k, v in adapter.calls[-1].items() if k != "file"} == want


def test_adapter_never_sends_keywords_to_a_model_that_rejects_them():
    assert "keywords" not in OpenAIProvider("whisper-1", client=FakeClient()).request(["Kondapur"])


def test_keyed_judge_sends_the_engine_prompt(monkeypatch):
    seen = {}

    def fake(model, system, user, name, schema, timeout):
        seen.update(model=model, system=system, user=user, name=name, schema=schema, timeout=timeout)
        return {"choice": "keep", "reason": "x"}

    monkeypatch.setattr(verifier, "structured_completion", fake)
    options = [{"text": "Kondapur", "source": "saved_places", "distance": 0.2}]
    verifier.OpenAIJudge(cache_answers=False).decide("at Kothapur", "Kothapur", "PLACE", options, None)
    fake_client = FakeClient()
    KeyedJudge(fake_client).decide("at Kothapur", "Kothapur", "PLACE", options, None)
    sent = fake_client.chats[0]
    assert sent["model"] == seen["model"] and sent["timeout"] == seen["timeout"]
    assert sent["messages"][0]["content"] == seen["system"] and sent["messages"][1]["content"] == seen["user"]
    assert sent["response_format"]["json_schema"]["schema"] == seen["schema"]
    assert sent["response_format"]["json_schema"]["name"] == seen["name"]


def test_verify_transcript_matches_the_engine_on_labelled_calls(client):
    sdk = client()
    for clip in corpus()[:20]:
        ctx = CallContext.build(clip["context"], "C3")
        engine = build_pipeline(judge=None, memory=sdk.memory).run(clip["text"], ctx, None, clip.get("second_opinion"))
        result = sdk.verify_transcript(clip["text"], clip["context"], alt_text=clip.get("second_opinion"))
        assert result.verified_text == engine.text_out


def test_heard_is_not_reported_as_verified(client):
    result = client().verify_transcript("Mera number 9848012345 hai")
    phone = next(f for f in result.entities if f.type == "PHONE")
    assert phone.status == "HEARD"


def test_phone_found_in_context_is_verified_and_digits_are_never_rewritten(client):
    sdk = client(contacts=[{"name": "Ravi", "number": "9848012345"}])
    assert (
        next(f for f in sdk.verify_transcript("Mera number 9848012345 hai").entities if f.type == "PHONE").status
        == "VERIFIED"
    )
    changed = sdk.verify_transcript("Mera number 9848012346 hai")
    assert "9848012346" in changed.verified_text


def test_numbers_cannot_be_learned(client):
    verdict = client().confirm_correction("u1", "9848012345", "9848012346", "PHONE")
    assert not verdict.adopted


def test_a_name_is_learned_only_through_the_checks_and_then_applies(client):
    sdk = client()
    assert not sdk.confirm_correction("u1", "Kondapur", "Mumbai", "PLACE").adopted
    assert sdk.confirm_correction("u1", "Rajeshwaree", "Rajeshwari", "PERSON").adopted
    assert "Rajeshwari" in sdk.verify_transcript("Main Rajeshwaree bol rahi hoon", {"user_id": "u1"}).verified_text
    assert "Rajeshwaree" in sdk.verify_transcript("Main Rajeshwaree bol rahi hoon", {"user_id": "u2"}).verified_text


def test_custom_provider_receives_keywords_and_wraps_any_model(client):
    seen = {}

    def my_stt(audio, keywords):
        seen.update(audio=audio, keywords=keywords)
        return "Main Ravi Kumar bol raha hoon"

    provider = CustomTranscriptProvider(my_stt, name="deepgram-nova")
    assert isinstance(provider, STTProvider)
    result = client(provider, contacts=[{"name": "Ravi Kumar"}]).verify_audio(b"audio-bytes")
    assert seen["audio"] == b"audio-bytes" and "Ravi Kumar" in seen["keywords"]
    assert result.telemetry.model == "deepgram-nova" and result.telemetry.evidence == "unmeasured"


@pytest.mark.parametrize(
    "model,evidence,second",
    [
        ("gpt-transcribe", "exam", "gpt-transcribe"),
        ("gpt-4o-transcribe", "dev", "gpt-transcribe"),
        ("gpt-4o-mini-transcribe", "dev", "gpt-transcribe"),
        ("whisper-1", "dev", "gpt-transcribe"),
    ],
)
def test_only_the_measured_setup_carries_its_evidence_label(client, model, evidence, second):
    provider = OpenAIProvider(model, client=FakeClient("Main Ravi bol raha hoon"))
    result = client(provider, judge=None, contacts=[{"name": "Ravi"}]).verify_audio(b"x")
    assert result.telemetry.evidence == evidence and result.telemetry.second_opinion_model == second


def test_changing_the_request_drops_the_exam_label(client):
    provider = OpenAIProvider("gpt-transcribe", client=FakeClient("hello"))
    result = client(provider, judge=None, contacts=[{"name": "Ravi"}]).verify_audio(b"x", language="hi")
    assert result.telemetry.evidence == "unmeasured"


def test_exam_setup_sends_keywords_first_and_a_plain_second_opinion(client):
    fake = FakeClient("Main Ravi bol raha hoon")
    client(OpenAIProvider("gpt-transcribe", client=fake), judge=None, contacts=[{"name": "Ravi"}]).verify_audio(b"x")
    assert sorted("keywords" in c for c in fake.calls) == [False, True]


def test_one_question_and_money_comes_first(client):
    from pehchaan_sdk.client import ASK_FIRST

    assert ASK_FIRST[:3] == ("PHONE", "AMOUNT", "PIN")
    result = client().verify_transcript("Mera number 98480123 hai")
    assert result.clarifier_prompt and result.clarifier_prompt == next(
        f.question for f in result.entities if f.status == "FLAGGED"
    )


def test_asr_result_is_the_only_contract_a_provider_needs(client):
    class Mine:
        def transcribe(self, audio, keywords=None):
            return ASRResult(text="Mera PIN 500032 hai", model="mine", latency_ms=7)

    result = client(Mine()).verify_audio(b"x")
    assert result.telemetry.stt_ms == 7 and any(f.type == "PIN" for f in result.entities)
