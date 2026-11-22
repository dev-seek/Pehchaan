"""
A labelled stand-in for speech, so the whole product runs on a machine with no API key (D-058).

It does not listen. It returns one fixed, invented line, so what comes after speech can be used end to end. It turns on
only when asked, only with no key, and never on a production server.
"""

from __future__ import annotations

import json
import os
import threading
from functools import lru_cache

from pehchaan.config import ROOT
from pehchaan_sdk import ASRResult, AudioFile

MODEL = "mock-speech"


def mock_speech_on() -> bool:
    return (
        os.environ.get("PEHCHAAN_MOCK_SPEECH") == "1"
        and os.environ.get("ENV") != "production"
        and not os.environ.get("OPENAI_API_KEY")
    )


@lru_cache(maxsize=1)
def _script() -> dict:
    return json.loads((ROOT / "data/demo/mock_speech.json").read_text(encoding="utf-8"))


class MockSpeech:
    """A whole file gets the whole line. Live phrases get it one part at a time, so a call does not repeat itself."""

    supports_keywords = True
    model = MODEL

    def __init__(self) -> None:
        self._next = 0
        self._lock = threading.Lock()

    def transcribe(self, audio, keywords=None, *, language=None, prompt=None) -> ASRResult:  # noqa: ARG002
        phrases = _script()["phrases"]
        if AudioFile.of(audio).name != "phrase.wav":
            return ASRResult(text=" ".join(phrases), model=MODEL, latency_ms=0)
        with self._lock:
            at, self._next = self._next, self._next + 1
        text = phrases[at] if at < len(phrases) else _script()["after_the_last_phrase"]
        return ASRResult(text=text, model=MODEL, latency_ms=0)
