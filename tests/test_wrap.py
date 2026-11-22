"""wrap() puts the harness on any speech model, and no language without number rules can have its money changed."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import tomllib
from openai import AsyncAzureOpenAI, AsyncOpenAI, AzureOpenAI, OpenAI

from pehchaan.config import ROOT, settings
from pehchaan.resolvers import NullMemoryStore
from pehchaan_sdk import CustomTranscriptProvider, Pehchaan, wrap
from pehchaan_sdk.cli import main
from pehchaan_sdk.wrap import VerifiedText, read_text

HEARD = "Main Ravi Kumaar bol raha hoon, mera number 9848012345 hai"
CONTACTS = [{"name": "Ravi Kumar", "number": "9848012345"}]


@pytest.fixture(autouse=True)
def private_state(monkeypatch, tmp_path):
    monkeypatch.setattr("pehchaan_sdk.client._state_dir", lambda: tmp_path)


def engine():
    return Pehchaan(CustomTranscriptProvider(), judge=None, memory=NullMemoryStore())


@pytest.mark.parametrize(
    "answer",
    [
        HEARD,
        {"text": HEARD},
        SimpleNamespace(text=HEARD),
        {"request_id": "1", "transcript": HEARD, "language_code": "hi-IN"},  # Sarvam
        {"results": {"channels": [{"alternatives": [{"transcript": HEARD, "confidence": 0.9}]}]}},  # Deepgram
        {"results": [{"alternatives": [{"transcript": HEARD}]}]},  # Google
        {"RecognitionStatus": "Success", "DisplayText": HEARD},  # Azure
    ],
)
def test_wrap_reads_every_common_speech_answer(answer):
    assert read_text(answer) == HEARD
    result = wrap(lambda _: answer, contacts=CONTACTS)("call.wav")
    assert isinstance(result, VerifiedText)
    assert result.startswith("Main Ravi Kumar bol")
    assert {f.type for f in result.pehchaan.entities} == {"PERSON", "PHONE"}


def test_wrap_refuses_an_answer_it_cannot_read():
    with pytest.raises(ValueError, match="Could not find a transcript"):
        wrap(lambda _: {"unknown": 1})("call.wav")


def test_wrap_accepts_context_per_call_and_a_second_model():
    def base(_):
        return "Main Rohit bol raha hoon"

    def other(_):
        return "Main Rohit bol raha hoon"

    result = wrap(base, second=other)("call.wav", pehchaan={"contacts": [{"name": "Mohit"}]})
    assert "Rohit" in result
    assert result.pehchaan.alt_text == "Main Rohit bol raha hoon"


def test_wrap_works_with_an_async_function():
    async def base(_):
        return {"transcript": HEARD}

    result = asyncio.run(wrap(base, contacts=CONTACTS)("call.wav"))
    assert result.startswith("Main Ravi Kumar bol")


class FakeOpenAI:
    base_url = "https://api.openai.com/v1/"

    def __init__(self):
        self.calls = []
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=None))
        self.models = "untouched"

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=HEARD, duration=3.0)


def test_wrapped_client_uses_keywords_and_a_second_opinion():
    client = FakeOpenAI()
    wrapped = wrap(client, contacts=CONTACTS)
    answer = wrapped.audio.transcriptions.create(model="gpt-transcribe", file=("call.wav", b"audio"))
    assert answer.text.startswith("Main Ravi Kumar bol")
    assert answer.pehchaan.telemetry.evidence == "unmeasured"  # the exam did not include the meaning layer
    assert len(client.calls) == 2
    assert sum("keywords" in call for call in client.calls) == 1
    assert wrapped.models == "untouched"


def test_wrapped_client_keeps_a_custom_request_and_its_extra_fields():
    client = FakeOpenAI()
    client.base_url = "https://example.openai.azure.com/"
    answer = wrap(client, contacts=CONTACTS).audio.transcriptions.create(
        model="my-deployment", file=("call.wav", b"audio"), temperature=0
    )
    assert len(client.calls) == 1 and client.calls[0]["temperature"] == 0
    assert answer.duration == 3.0
    assert answer.text.startswith("Main Ravi Kumar bol")
    assert answer.pehchaan.telemetry.evidence == "unmeasured"


def test_wrapped_client_refuses_to_pass_a_stream_through_unchecked():
    with pytest.raises(ValueError, match="/v1/stream"):
        wrap(FakeOpenAI()).audio.transcriptions.create(model="gpt-transcribe", file=("a.wav", b"a"), stream=True)


def _speech_server(request: httpx.Request) -> httpx.Response:
    body = request.read()
    if b'name="response_format"\r\n\r\ntext' in body:
        return httpx.Response(200, text=HEARD, headers={"content-type": "text/plain"})
    return httpx.Response(200, json={"text": HEARD, "language": "hindi", "duration": 3.0, "segments": []})


def _sync_http():
    return httpx.Client(transport=httpx.MockTransport(_speech_server))


def _async_http():
    return httpx.AsyncClient(transport=httpx.MockTransport(_speech_server))


AZURE = {"api_key": "k", "api_version": "2025-01-01", "azure_endpoint": "https://x.openai.azure.com"}


@pytest.mark.parametrize("response_format", [None, "json", "text", "verbose_json"])
def test_the_real_openai_client_keeps_its_answer_shape(response_format):
    options = {"response_format": response_format} if response_format else {}
    client = wrap(OpenAI(api_key="sk-x", http_client=_sync_http()), contacts=CONTACTS, memory=NullMemoryStore())
    answer = client.audio.transcriptions.create(model="whisper-1", file=("a.wav", b"audio"), **options)
    assert str(getattr(answer, "text", answer)).startswith("Main Ravi Kumar bol")
    assert answer.pehchaan.entities


def test_the_real_azure_client_is_checked_as_unmeasured():
    client = wrap(AzureOpenAI(**AZURE, http_client=_sync_http()), contacts=CONTACTS, memory=NullMemoryStore())
    answer = client.audio.transcriptions.create(model="my-deployment", file=("a.wav", b"audio"))
    assert answer.text.startswith("Main Ravi Kumar bol") and answer.pehchaan.telemetry.evidence == "unmeasured"


@pytest.mark.parametrize(
    "make",
    [
        lambda: AsyncOpenAI(api_key="sk-x", http_client=_async_http()),
        lambda: AsyncAzureOpenAI(**AZURE, http_client=_async_http()),
    ],
)
def test_the_real_async_clients_work(make):
    async def run():
        client = wrap(make(), contacts=CONTACTS, memory=NullMemoryStore())
        return await client.audio.transcriptions.create(model="my-deployment", file=("a.wav", b"audio"), temperature=0)

    assert asyncio.run(run()).text.startswith("Main Ravi Kumar bol")


@pytest.mark.parametrize("response_format", ["srt", "vtt"])
def test_subtitle_formats_are_refused_rather_than_corrupted(response_format):
    with pytest.raises(ValueError, match="subtitle"):
        wrap(FakeOpenAI()).audio.transcriptions.create(
            model="whisper-1", file=("a.wav", b"a"), response_format=response_format
        )


def test_silence_from_a_google_style_answer_is_an_empty_transcript():
    assert read_text({"results": []}) == ""


def test_money_in_a_language_without_number_rules_is_never_changed():
    spoken = "બે હજાર રૂપિયા આપો"  # Gujarati: "give two thousand rupees"
    result = engine().verify_transcript(spoken)
    assert result.verified_text == spoken
    amount = next(f for f in result.entities if f.type == "AMOUNT")
    assert amount.status == "FLAGGED" and "1000" not in amount.value
    assert result.clarifier_prompt


def test_a_declared_language_without_number_rules_also_keeps_the_words():
    spoken = "दोन लाख रुपये द्या"  # Marathi uses the Hindi script, so only the declared language can reveal it
    result = engine().verify_transcript(spoken, language="mr")
    assert result.verified_text == spoken
    assert all(f.status == "FLAGGED" for f in result.entities if f.type == "AMOUNT")


@pytest.mark.parametrize("language", [None, "hi", "hi-IN"])
def test_supported_languages_keep_reading_numbers(language):
    result = engine().verify_transcript("दो हज़ार रुपये दीजिए", language=language)
    amount = next(f for f in result.entities if f.type == "AMOUNT")
    assert amount.value == "2000" and amount.status != "FLAGGED"


def test_cli_checks_a_transcript_without_a_key(capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["--text", HEARD, "--contact", "Ravi Kumar"]) == 0
    out = capsys.readouterr().out
    assert "Main Ravi Kumar bol" in out and "verified" in out


def test_reads_google_answers_whose_results_are_not_a_plain_list():
    from collections.abc import Sequence
    from types import SimpleNamespace as Obj

    class Repeated(Sequence):  # how Google's client library returns repeated fields
        def __init__(self, *items):
            self.items = items

        def __getitem__(self, index):
            return self.items[index]

        def __len__(self):
            return len(self.items)

    part = Obj(alternatives=Repeated(Obj(transcript="Ravi Kumar")))
    assert read_text(Obj(results=Repeated(part, part))) == "Ravi Kumar Ravi Kumar"
    assert read_text(Obj(results=Repeated())) == ""


def test_the_installed_package_ships_every_data_file_the_sdk_reads():
    """A pip install has only what pyproject lists, so a forgotten data file crashes every customer's first call."""
    build = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]
    shipped = build["targets"]["wheel"]["force-include"]
    needed = Path(settings()["sdk"]["number_forms"])
    assert any(needed == Path(item) or Path(item) in needed.parents for item in shipped)
