"""
Speech-to-text via OpenAI, cached. Model names come from settings.yaml, never from code.

Verified on the team key (tools/check_openai.py, 21 Nov):
  * gpt-4o-transcribe / gpt-4o-mini-transcribe return per-token `logprobs` with include=["logprobs"], json format
  * gpt-transcribe supports `keywords` and `languages`; no logprobs
  * gpt-transcribe and gpt-4o-mini-transcribe write phone numbers as English words in Devanagari ("नाइन एट फोर")
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..openai_client import cached, client


def _audio_fingerprint(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:20]


def transcribe(audio_path: str | Path, model: str, *, keywords: list[str] | None = None,
               languages: list[str] | None = None, prompt: str | None = None,
               with_logprobs: bool = False, timeout: float = 90) -> dict:
    """Returns {text, tokens: [{token, logprob}], latency_ms, cached, model}."""
    audio_path = Path(audio_path)
    params: dict = {"model": model}
    if keywords:
        params["keywords"] = list(keywords)
    if languages and model.startswith("gpt-transcribe"):
        params["languages"] = list(languages)
    if prompt:
        params["prompt"] = prompt
    if with_logprobs:
        params["include"] = ["logprobs"]
        params["response_format"] = "json"

    def call() -> dict:
        with open(audio_path, "rb") as f:
            r = client().audio.transcriptions.create(file=f, timeout=timeout, **params)
        d = r.model_dump() if hasattr(r, "model_dump") else {"text": str(r)}
        tokens = [{"token": x.get("token", ""), "logprob": x.get("logprob")} for x in (d.get("logprobs") or [])]
        return {"text": d.get("text", ""), "tokens": tokens}

    answer, was_cached = cached("asr", {"audio": _audio_fingerprint(audio_path), **params}, call)
    return {**answer, "latency_ms": answer.get("_ms", 0), "cached": was_cached, "model": model}
