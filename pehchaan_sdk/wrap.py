"""
One line that puts the harness on top of a speech model you already use.

    client = wrap(OpenAI())                    # your OpenAI, AsyncOpenAI or AzureOpenAI client, used the same way
    transcribe = wrap(my_speech_function)      # any function that returns a transcript

The answer keeps its normal shape. Its text is the checked text, and `.pehchaan` holds the facts and the question to ask.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from urllib.parse import urlparse

from pehchaan.config import settings

from .client import Pehchaan
from .judge import KeyedJudge
from .knowledge import as_hub
from .providers import AudioFile, CustomTranscriptProvider, OpenAIProvider
from .types import VerifyResult

_SIMPLE_ARGS = frozenset({"file", "model", "language", "prompt", "response_format"})
_PLAIN_FORMATS = (None, "json", "text")
_TIMED_FORMATS = ("srt", "vtt")


class VerifiedText(str):
    """A normal string holding the checked transcript, with the details on `.pehchaan`."""

    pehchaan: VerifyResult

    def __new__(cls, result: VerifyResult):
        text = super().__new__(cls, result.verified_text)
        text.pehchaan = result
        return text


def _field(item, name: str):
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def _first_alternative(item) -> str | None:
    alternatives = _field(item, "alternatives")
    return _field(alternatives[0], "transcript") if alternatives else None


def read_text(answer) -> str:
    """Find the transcript in the answer of OpenAI, Sarvam, Deepgram, Google, Azure, AssemblyAI, or a plain string."""
    if isinstance(answer, str):
        return answer
    for name in ("text", "transcript", "DisplayText"):
        value = _field(answer, name)
        if isinstance(value, str):
            return value
    results = _field(answer, "results")
    channels = _field(results, "channels") if results is not None and not isinstance(results, list | tuple) else None
    if channels:
        value = _first_alternative(channels[0])  # Deepgram
        if isinstance(value, str):
            return value
    if results is not None and not channels:
        parts = [_first_alternative(r) for r in results]  # Google. Silence gives an empty list.
        if all(isinstance(p, str) for p in parts):
            return " ".join(p.strip() for p in parts)
    raise ValueError("Could not find a transcript in this answer. Return the text from your function.")


def _audio(file) -> AudioFile:
    if isinstance(file, tuple):
        name, content = file[0], file[1]
        content = content if isinstance(content, bytes | bytearray) else content.read()
        return AudioFile(Path(str(name or "call.wav")).name, bytes(content))
    return AudioFile.of(file)


def _is_async(create) -> bool:
    """The OpenAI SDK hides `async def` behind a plain decorator, so look underneath it."""
    return inspect.iscoroutinefunction(inspect.unwrap(create))


def _is_openai(client) -> bool:
    host = urlparse(str(getattr(client, "base_url", ""))).hostname or ""
    return host == "api.openai.com" and "azure" not in type(client).__name__.lower()


class _Transcriptions:
    def __init__(self, owner: _WrappedClient):
        self._owner = owner
        self._inner = owner._client.audio.transcriptions

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def create(self, *, pehchaan: dict | None = None, **kwargs):
        if kwargs.get("stream"):
            raise ValueError("wrap() checks complete transcripts. For live audio use the /v1/stream WebSocket.")
        if kwargs.get("response_format") in _TIMED_FORMATS:
            raise ValueError("wrap() cannot check subtitle files. Use response_format='json' or 'verbose_json'.")
        kwargs["file"] = (lambda a: (a.name, a.content))(_audio(kwargs["file"]))
        if _is_async(self._inner.create):
            return self._create_async(pehchaan, kwargs)
        if self._owner.measured_setup(kwargs):
            return self._shape(self._owner.verify_audio(self._owner._client, kwargs, pehchaan), kwargs)
        answer = self._inner.create(**kwargs)
        return self._replace(answer, self._owner.verify_text(read_text(answer), kwargs, pehchaan))

    async def _create_async(self, context: dict | None, kwargs: dict):
        if self._owner.measured_setup(kwargs):
            sync = self._owner.sync_client()
            return self._shape(await asyncio.to_thread(self._owner.verify_audio, sync, kwargs, context), kwargs)
        answer = await self._inner.create(**kwargs)
        result = await asyncio.to_thread(self._owner.verify_text, read_text(answer), kwargs, context)
        return self._replace(answer, result)

    @staticmethod
    def _shape(result: VerifyResult, kwargs: dict):
        if kwargs.get("response_format") == "text":
            return VerifiedText(result)
        from openai.types.audio import Transcription

        answer = Transcription(text=result.verified_text)
        answer.pehchaan = result
        return answer

    @staticmethod
    def _replace(answer, result: VerifyResult):
        if isinstance(answer, str):
            return VerifiedText(result)
        answer.text = result.verified_text
        answer.pehchaan = result
        return answer


class _Audio:
    def __init__(self, owner: _WrappedClient):
        self._inner = owner._client.audio
        self.transcriptions = _Transcriptions(owner)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _WrappedClient:
    """Your client, unchanged, except that audio transcriptions come back checked."""

    def __init__(self, client, context: dict):
        self._client = client
        self._context = context
        self.audio = _Audio(self)

    def __getattr__(self, name):
        return getattr(self._client, name)

    def measured_setup(self, kwargs: dict) -> bool:
        """Only a plain request to a known OpenAI model can use keywords and a second opinion, as the benchmark did."""
        return (
            _is_openai(self._client)
            and kwargs.get("model") in settings()["sdk"]["models"]
            and set(kwargs) <= _SIMPLE_ARGS
            and kwargs.get("response_format") in _PLAIN_FORMATS
        )

    def sync_client(self):
        from openai import OpenAI

        return OpenAI(
            api_key=self._client.api_key, base_url=self._client.base_url, organization=self._client.organization
        )

    def verify_audio(self, client, kwargs: dict, context: dict | None) -> VerifyResult:
        provider = OpenAIProvider(kwargs["model"], client=client)
        engine = Pehchaan(provider, **self._context)
        return engine.verify_audio(
            AudioFile(*kwargs["file"]), context, language=kwargs.get("language"), prompt=kwargs.get("prompt")
        )

    def verify_text(self, text: str, kwargs: dict, context: dict | None) -> VerifyResult:
        judge = None
        if _is_openai(self._client):
            is_async = _is_async(self._client.audio.transcriptions.create)
            judge = KeyedJudge(self.sync_client() if is_async else self._client)
        engine = Pehchaan(CustomTranscriptProvider(), judge=judge, **self._context)
        return engine.verify_transcript(
            text, context, model=str(kwargs.get("model", "external")), language=kwargs.get("language")
        )


class _WrappedFunction:
    def __init__(self, function, second, context: dict):
        self._function, self._second = function, second
        self._engine = Pehchaan(
            CustomTranscriptProvider(name=getattr(function, "__name__", "external")), judge=None, **context
        )
        self._name = getattr(function, "__name__", "external")

    @staticmethod
    def _rewind(args, kwargs) -> None:
        for item in (*args, *kwargs.values()):
            if hasattr(item, "seek"):
                item.seek(0)

    def _verify(self, answer, other, context, language) -> VerifiedText:
        alt = read_text(other) if other is not None else None
        return VerifiedText(
            self._engine.verify_transcript(read_text(answer), context, alt, model=self._name, language=language)
        )

    def __call__(self, *args, pehchaan: dict | None = None, pehchaan_language: str | None = None, **kwargs):
        answer = self._function(*args, **kwargs)
        if inspect.isawaitable(answer):
            return self._finish_async(answer, args, kwargs, pehchaan, pehchaan_language)
        other = None
        if self._second is not None:
            self._rewind(args, kwargs)
            other = self._second(*args, **kwargs)
        return self._verify(answer, other, pehchaan, pehchaan_language)

    async def _finish_async(self, pending, args, kwargs, context, language):
        answer = await pending
        other = None
        if self._second is not None:
            self._rewind(args, kwargs)
            other = self._second(*args, **kwargs)
            other = await other if inspect.isawaitable(other) else other
        return await asyncio.to_thread(self._verify, answer, other, context, language)


def wrap(target, *, second=None, **context):
    """
    Put Pehchaan on top of a speech model. `target` is an OpenAI-style client or any function that returns a transcript.

    Call facts go here or per call as `pehchaan={...}`: city, contacts, recent_sms, places, caller, domain, user_id.
    `second` is an optional second speech function. An independent transcript makes the check stronger.
    `knowledge` connects company systems (a source, a list of sources, or a KnowledgeHub). They are asked about each call
    using `caller` or `customer_id`, and their records count as evidence, never as the truth.
    """
    if context.get("knowledge") is not None:
        context["knowledge"] = as_hub(context["knowledge"])  # one hub, so its cache survives across calls
    transcriptions = getattr(getattr(target, "audio", None), "transcriptions", None)
    if transcriptions is not None and hasattr(transcriptions, "create"):
        if second is not None:
            raise ValueError(
                "`second` is for wrapped functions. OpenAI clients choose their second opinion automatically."
            )
        return _WrappedClient(target, context)
    if callable(target):
        return _WrappedFunction(target, second, context)
    raise TypeError("wrap() takes an OpenAI-style client or a function that returns a transcript")
