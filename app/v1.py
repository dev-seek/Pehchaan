"""
The versioned public API: an OpenAI-compatible proxy plus plain verify endpoints. Contract: docs/API.md.

Live paths never cache audio, transcripts or keys. Everything measured comes from data/published.
"""

from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, ValidationError

from bench.manifest import frozen_changes, run_manifest
from pehchaan.config import ROOT, settings
from pehchaan.resolvers import JsonMemoryStore
from pehchaan_sdk import AudioFile, CustomTranscriptProvider, OpenAIProvider, Pehchaan, VerifyResult
from pehchaan_sdk.judge import KeyedJudge
from pehchaan_sdk.types import CorrectionResult

from .access import Credential, authenticate, is_public, passcode, require_inference, spend
from .audio_guard import check_audio, read_upload
from .demo_api import _Context

router = APIRouter(tags=["Verify"])
PUBLISHED = ROOT / "data" / "published"
_logger = logging.getLogger(__name__)
_memory = JsonMemoryStore(ROOT / settings()["api"]["memory_dir"])
_active = {"n": 0}


class TranscriptRequest(BaseModel):
    text: str = Field(min_length=1, description="The transcript from any speech-to-text model")
    context: dict | None = Field(default=None, description="What the phone knows: user, caller, contacts, sms, places")
    alt_text: str | None = Field(default=None, description="Optional second transcript of the same audio")
    model: str = Field(default="external", description="Name of the speech model, for your telemetry")
    language: str | None = Field(default=None, description="Language code, for example hi or ta. See docs/LANGUAGES.md")


class MemoryRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    heard: str = Field(min_length=1, max_length=100)
    corrected: str = Field(min_length=1, max_length=100)
    entity_type: str


def scoped_user(credential: Credential, user_id: str) -> str:
    """Two customers can use the same user id without ever sharing a memory."""
    import hashlib

    return hashlib.sha256(f"{credential.tenant}:{user_id}".encode()).hexdigest()[:32]


def parse_context(raw: str | dict | None, credential: Credential) -> dict:
    if raw is None or raw == "":
        return {}
    text = raw if isinstance(raw, str) else json.dumps(raw)
    if len(text) > settings()["demo"]["max_context_chars"]:
        raise HTTPException(413, "context is too large")
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError
        clean = _Context.model_validate(data).model_dump(exclude_none=True)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "context must be a valid call context JSON object") from exc
    user_id = data.get("user_id") or (data.get("user") or {}).get("id")
    if user_id:
        clean.setdefault("user", {})["id"] = scoped_user(credential, str(user_id)[:80])
    return clean


def clean_language(value: str | None) -> str | None:
    if not value:
        return None
    if not re.fullmatch(r"[A-Za-z]{2,3}(-[A-Za-z]{2,4})?", value):
        raise HTTPException(400, "language must be a code such as hi, ta or hi-IN.")
    return value


def server_has_key() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def speech_provider(model: str | None, credential: Credential) -> OpenAIProvider:
    model = model or settings()["sdk"]["default_model"]
    if model not in settings()["sdk"]["models"]:
        raise HTTPException(400, f"Unsupported model. Choose one of: {', '.join(settings()['sdk']['models'])}")
    if not credential.openai_key and not server_has_key():
        raise HTTPException(503, "No OpenAI key is configured on this server. Send your own in X-OpenAI-Key.")
    return OpenAIProvider(model, api_key=credential.openai_key)


def engine_for(provider, credential: Credential) -> Pehchaan:
    judge = None
    if credential.openai_key or server_has_key():
        keyed = provider if isinstance(provider, OpenAIProvider) else OpenAIProvider(api_key=credential.openai_key)
        judge = KeyedJudge(keyed.client)
    return Pehchaan(provider, judge=judge, memory=_memory, ledger=ROOT / settings()["api"]["ledger_db"])


def upstream_error(exc: Exception) -> HTTPException:
    """Report what went wrong without repeating anything from the upstream message, which can quote a key."""
    import openai

    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, openai.AuthenticationError):
        return HTTPException(401, "OpenAI rejected this key.")
    if isinstance(exc, openai.RateLimitError):
        return HTTPException(429, "OpenAI is rate limiting this key. Try again shortly.")
    if isinstance(exc, openai.BadRequestError):
        return HTTPException(400, "The speech model could not process this audio.")
    _logger.warning("live request failed (%s)", type(exc).__name__)
    return HTTPException(502, "The speech model is unavailable. Try again shortly.")


class _Slot:
    """Refuse extra live work instead of queueing it behind a small server."""

    def __enter__(self):
        if _active["n"] >= settings()["demo"]["max_active_runs"]:
            raise HTTPException(429, "The server is busy. Try again in a moment.")
        _active["n"] += 1

    def __exit__(self, *_):
        _active["n"] -= 1


async def verify_upload(
    request: Request,
    upload: UploadFile,
    raw_context,
    model: str | None,
    credential: Credential,
    language: str | None = None,
    prompt: str | None = None,
) -> VerifyResult:
    provider = speech_provider(model, credential)
    context = parse_context(raw_context, credential)
    language = clean_language(language)
    content, extension = await read_upload(upload)
    await run_in_threadpool(check_audio, content, extension)
    spend(request, credential)
    with _Slot():
        try:
            return await run_in_threadpool(
                engine_for(provider, credential).verify_audio,
                AudioFile(f"call{extension}", content),
                context,
                language=language or None,
                prompt=prompt or None,
            )
        except Exception as exc:  # noqa: BLE001
            raise upstream_error(exc) from exc


@router.post("/v1/audio/transcriptions", tags=["OpenAI drop-in"], summary="OpenAI-compatible transcription, verified")
async def openai_proxy(
    request: Request,
    file: Annotated[UploadFile, File()],
    model: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    prompt: Annotated[str | None, Form()] = None,
    response_format: Annotated[str, Form()] = "json",
    stream: Annotated[str | None, Form()] = None,
    x_pehchaan_context: Annotated[str | None, Header()] = None,
    x_demo_passcode: Annotated[str | None, Header()] = None,
    x_openai_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
):
    """Point an OpenAI client's `base_url` at `/v1`. Send call context as JSON in the `X-Pehchaan-Context` header."""
    try:
        if response_format not in ("json", "text"):
            raise HTTPException(400, "response_format must be json or text.")
        if stream and stream.lower() == "true":
            raise HTTPException(400, "Streaming is available at WS /v1/stream.")
        credential = authenticate(
            request, demo_passcode=x_demo_passcode, openai_key=x_openai_key, authorization=authorization
        )
        result = await verify_upload(request, file, x_pehchaan_context, model, credential, language, prompt)
    except HTTPException as exc:
        return JSONResponse(
            {"error": {"message": exc.detail, "type": "invalid_request_error", "code": exc.status_code}},
            status_code=exc.status_code,
        )
    if response_format == "text":
        return PlainTextResponse(result.verified_text)
    details = result.model_dump(exclude={"verified_text"})
    details["flags"] = [f for f in details["entities"] if f["status"] == "FLAGGED"]
    return {"text": result.verified_text, "pehchaan": details}


@router.post("/v1/verify-audio", response_model=VerifyResult, summary="Transcribe with a chosen model, then verify")
async def verify_audio(
    request: Request,
    audio: Annotated[UploadFile, File()],
    context: Annotated[str | None, Form()] = None,
    model: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
    credential: Credential = Depends(require_inference),
):
    return await verify_upload(request, audio, context, model, credential, language)


@router.post("/v1/verify-transcript", response_model=VerifyResult, summary="Verify the output of any speech model")
async def verify_transcript(
    request: Request, body: TranscriptRequest, credential: Credential = Depends(require_inference)
):
    limit = settings()["demo"]["max_text_chars"]
    if len(body.text) > limit or len(body.alt_text or "") > limit:
        raise HTTPException(413, f"Transcript is longer than {limit} characters.")
    context = parse_context(body.context, credential)
    language = clean_language(body.language)
    spend(request, credential)
    with _Slot():
        try:
            return await run_in_threadpool(
                engine_for(CustomTranscriptProvider(), credential).verify_transcript,
                body.text,
                context,
                body.alt_text,
                model=body.model[:60],
                language=language,
            )
        except Exception as exc:  # noqa: BLE001
            raise upstream_error(exc) from exc


@router.post(
    "/v1/memory/confirm", response_model=CorrectionResult, summary="Teach a confirmed name, after safety checks"
)
async def memory_confirm(request: Request, body: MemoryRequest, credential: Credential = Depends(require_inference)):
    """Phone numbers, PINs and money can never be learned. Memory is private to your credential."""
    spend(request, credential)
    sdk = Pehchaan(CustomTranscriptProvider(), judge=None, memory=_memory, ledger=ROOT / settings()["api"]["ledger_db"])
    return await run_in_threadpool(
        sdk.confirm_correction, scoped_user(credential, body.user_id), body.heard, body.corrected, body.entity_type
    )


def _published(name: str) -> dict | None:
    file = PUBLISHED / name
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else None


@router.get("/v1/bench", tags=["Evidence"], summary="The published benchmark results")
def bench():
    return {
        "exam": {
            "standard": _published("benchmark_test_real_phone.json"),
            "noisy": _published("benchmark_test_real_noisy.json"),
        },
        "exam_paired": _published("exam_paired.json"),
        "dev": _published("benchmark_dev.json"),
        "line_quality": _published("real_voice.json"),
        "models": _published("model_compare.json"),
        "languages": _published("language_support.json"),
        "model_profiles": settings()["sdk"]["models"],
    }


@lru_cache(maxsize=1)
def _engine_matches_exam() -> bool | None:
    exam = _published("benchmark_test_real_phone.json")
    return not frozen_changes(exam["manifest"], run_manifest()) if exam else None


@router.get("/health", tags=["Evidence"], summary="Is the service up, and is it the engine that sat the exam?")
def health():
    return {
        "status": "ok",
        "mode": "production" if is_public() else "local",
        "version": settings()["api"]["version"],
        "engine_matches_exam": _engine_matches_exam(),
        "live": {"passcode": bool(passcode()), "server_key": server_has_key(), "bring_your_own_key": True},
    }
