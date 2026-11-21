"""
Speech-to-text adapters. Anything with `transcribe(audio, keywords) -> ASRResult` can feed Pehchaan.

`OpenAIProvider` sends the same request as the engine's own `pehchaan.asr.transcribe`, with a key of its own and no answer
cache, so one customer's audio or key can never reach another's. A test holds the two request shapes equal.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

from pehchaan.config import settings

from .types import ASRResult

AudioInput = str | Path | bytes | BinaryIO


@dataclass(frozen=True)
class AudioFile:
    """Audio read once, so two transcribers can use it side by side."""

    name: str
    content: bytes

    @classmethod
    def of(cls, audio: AudioInput | AudioFile) -> AudioFile:
        if isinstance(audio, AudioFile):
            return audio
        if isinstance(audio, str | Path):
            file = Path(audio)
            return cls(file.name, file.read_bytes())
        if isinstance(audio, bytes | bytearray):
            return cls("call.wav", bytes(audio))
        return cls(Path(getattr(audio, "name", "call.wav")).name, audio.read())


@runtime_checkable
class STTProvider(Protocol):
    def transcribe(self, audio: AudioInput, keywords: list[str] | None = None) -> ASRResult: ...


def model_profile(model: str) -> dict:
    profile = settings()["sdk"]["models"].get(model)
    if profile is None:
        raise ValueError(f"unknown speech model {model!r}; choose one of {sorted(settings()['sdk']['models'])}")
    return profile


class OpenAIProvider:
    """One of the OpenAI speech models listed in `sdk.models` in config/settings.yaml."""

    def __init__(self, model: str | None = None, *, api_key: str | None = None, client=None):
        self.model = model or settings()["sdk"]["default_model"]
        self.profile = model_profile(self.model)
        self.api_key = api_key
        self._client = client

    @property
    def supports_keywords(self) -> bool:
        return bool(self.profile["keywords"])

    @property
    def has_key(self) -> bool:
        return bool(self._client or self.api_key or os.environ.get("OPENAI_API_KEY"))

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key) if self.api_key else OpenAI()
        return self._client

    def request(self, keywords: list[str] | None, language: str | None = None, prompt: str | None = None) -> dict:
        params: dict = {"model": self.model}
        if keywords and self.supports_keywords:
            params["keywords"] = list(keywords)
        if self.profile["languages"]:
            params["languages"] = [language] if language else list(settings()["asr"]["languages"])
        elif language:
            params["language"] = language
        if prompt:
            params["prompt"] = prompt
        return params

    def transcribe(
        self,
        audio: AudioInput,
        keywords: list[str] | None = None,
        *,
        language: str | None = None,
        prompt: str | None = None,
    ) -> ASRResult:
        file = AudioFile.of(audio)
        started = time.perf_counter()
        answer = self.client.audio.transcriptions.create(
            file=(file.name, file.content),
            timeout=settings()["asr"]["timeout_s"],
            **self.request(keywords, language, prompt),
        )
        text = answer.text if hasattr(answer, "text") else str(answer)
        return ASRResult(text=text, model=self.model, latency_ms=int((time.perf_counter() - started) * 1000))

    def second_opinion(self) -> OpenAIProvider:
        """The independent transcript the measured setups use: same model without keywords, or a different model."""
        if self.supports_keywords:
            return OpenAIProvider(self.model, api_key=self.api_key, client=self._client)
        return OpenAIProvider(settings()["sdk"]["second_opinion_model"], api_key=self.api_key, client=self._client)


class CustomTranscriptProvider:
    """
    Bring your own speech-to-text (Deepgram, Sarvam, Google, Azure, an in-house model).

    Pass a function that takes audio and optional keywords and returns text or an ASRResult. If your transcripts already
    exist you do not need this class: call `Pehchaan.verify_transcript` directly.
    """

    supports_keywords = True

    def __init__(self, transcribe_fn: Callable[..., str | ASRResult] | None = None, *, name: str = "external"):
        self.transcribe_fn = transcribe_fn
        self.model = name

    def transcribe(self, audio: AudioInput, keywords: list[str] | None = None) -> ASRResult:
        if self.transcribe_fn is None:
            raise ValueError("this provider has no transcribe function: use verify_transcript, or pass one")
        started = time.perf_counter()
        answer = self.transcribe_fn(AudioFile.of(audio).content, keywords)
        if isinstance(answer, ASRResult):
            return answer
        return ASRResult(text=str(answer), model=self.model, latency_ms=int((time.perf_counter() - started) * 1000))
