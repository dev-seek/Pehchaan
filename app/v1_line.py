"""
One recording, checked on its clear copy and on a worse phone line at the same time (D-057).

The noise is the benchmark's own line effect (`tools/make_audio.degrade` with the `real_check` profiles), and the score
comes from the benchmark's independent scorer. A fresh recording has no human label, so the reference is what both
systems agree on in the clear copy: a fact Pehchaan alone claims cannot count in its favour. Audio is never stored, and
these runs are not saved as calls.
"""

from __future__ import annotations

import asyncio
import base64
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from bench.oracle import fact_correct
from bench.score import score_clip
from pehchaan.config import settings
from pehchaan_sdk import AudioFile, VerifyResult
from tools.make_audio import degrade

from .access import Credential, require_inference, spend
from .audio_guard import check_audio, read_upload
from .mock_speech import MockSpeech
from .v1 import _Slot, clean_language, engine_for, parse_context, speech_provider, upstream_error

router = APIRouter(tags=["Verify"])
Verdict = Literal["right", "asked", "silent"]
_DECODE_RATE = 16000


class Tally(BaseModel):
    right: int
    asked: int
    silent: int


class Side(BaseModel):
    alone: Tally
    pehchaan: Tally


class LineFact(BaseModel):
    type: str
    value: str
    alone: Verdict
    pehchaan: Verdict


class LineTest(BaseModel):
    line: str
    clear: VerifyResult
    noisy: VerifyResult
    clear_alone: str
    noisy_alone: str
    noisy_audio: str
    noisy_score: Side
    facts: list[LineFact]


def worse_line(content: bytes, extension: str, line: str) -> bytes:
    """The recording as WAV after this line's effect. ffmpeg only ever sees it through the same locked-down decode."""
    limit = settings()["api"]["max_audio_seconds"]
    timeout = settings()["api"]["line_test"]["timeout_s"]
    with tempfile.TemporaryDirectory() as folder:
        source, decoded, out = (Path(folder) / name for name in (f"in{extension}", "clear.wav", "line.wav"))
        source.write_bytes(content)
        decode = ["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file", "-i", str(source)]
        decode += ["-map", "0:a:0", "-t", str(limit), "-ac", "1", "-ar", str(_DECODE_RATE), "-c:a", "pcm_s16le"]
        try:
            subprocess.run([*decode, str(decoded)], check=True, capture_output=True, timeout=timeout)
            degrade(decoded, out, timeout=timeout, **settings()["real_check"]["conditions"][line])
        except FileNotFoundError as exc:
            raise HTTPException(503, "Audio processing is not available on this server.") from exc
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(400, "This audio could not be put on a phone line.") from exc
        return out.read_bytes()


def speech_alone(result: VerifyResult) -> str:
    """The chosen model with no hints: the no-keyword transcript if it came from this model, else the main one."""
    same_model = result.alt_text is not None and result.telemetry.second_opinion_model == result.telemetry.model
    return result.alt_text if same_model else result.raw_text


def _verdict(row: dict) -> Verdict:
    return "right" if row["correct"] else "asked" if row["flagged"] else "silent"


def _tally(verdicts: list[Verdict]) -> Tally:
    return Tally(right=verdicts.count("right"), asked=verdicts.count("asked"), silent=verdicts.count("silent"))


def reference_facts(clear: VerifyResult) -> list[dict]:
    """Facts Pehchaan stated on the clear copy and speech alone also said. Doubted or Pehchaan-only facts are left out."""
    alone = speech_alone(clear)
    facts = {(f.type, f.value): {"type": f.type, "value": f.value} for f in clear.entities if f.status != "FLAGGED"}
    return [fact for fact in facts.values() if fact_correct(fact, alone)]


def score_against(reference: VerifyResult, answer: VerifyResult) -> tuple[Side, list[LineFact]]:
    """Score speech alone and Pehchaan on the same reference facts."""
    facts = reference_facts(reference)
    flags = [
        {"etype": f.type, "options": f.options, "surface": f.heard} for f in answer.entities if f.status == "FLAGGED"
    ]
    alone = score_clip(facts, reference.verified_text, speech_alone(answer), None, [])["entities"]
    checked = score_clip(facts, reference.verified_text, answer.verified_text, None, flags)["entities"]
    rows = [
        LineFact(type=f["type"], value=f["value"], alone=_verdict(a), pehchaan=_verdict(c))
        for f, a, c in zip(facts, alone, checked, strict=True)
    ]
    return Side(alone=_tally([r.alone for r in rows]), pehchaan=_tally([r.pehchaan for r in rows])), rows


@router.post("/v1/line-test", response_model=LineTest, summary="Check one recording on its clear copy and a noisy line")
async def line_test(
    request: Request,
    audio: Annotated[UploadFile, File()],
    credential: Annotated[Credential, Depends(require_inference)],
    line: Annotated[str, Form()] = "very_noisy",
    context: Annotated[str | None, Form()] = None,
    model: Annotated[str | None, Form()] = None,
    language: Annotated[str | None, Form()] = None,
):
    """Costs two verified calls. Each result is scored by the benchmark's scorer on the facts both systems agree on in the clear copy."""
    lines = settings()["api"]["line_test"]["lines"]
    if line not in lines:
        raise HTTPException(400, f"line must be one of: {', '.join(lines)}")
    if isinstance(speech_provider(model, credential), MockSpeech):
        raise HTTPException(503, "The noisy-line test needs a real speech model. Add an OpenAI key or use the live site.")
    clear_engine = engine_for(speech_provider(model, credential), credential)
    noisy_engine = engine_for(speech_provider(model, credential), credential)
    call_context = parse_context(context, credential)
    language = clean_language(language)
    content, extension = await read_upload(audio)
    await run_in_threadpool(check_audio, content, extension)
    noisy_bytes = await run_in_threadpool(worse_line, content, extension, line)
    spend(request, credential)
    spend(request, credential)
    with _Slot(), _Slot():
        try:
            clear, noisy = await asyncio.gather(
                run_in_threadpool(
                    clear_engine.verify_audio,
                    AudioFile(f"call{extension}", content),
                    call_context,
                    language=language or None,
                ),
                run_in_threadpool(
                    noisy_engine.verify_audio, AudioFile("call.wav", noisy_bytes), call_context, language=language or None
                ),
            )
        except Exception as exc:  # noqa: BLE001
            raise upstream_error(exc) from exc
    noisy_score, facts = await run_in_threadpool(score_against, clear, noisy)
    return LineTest(
        line=line,
        clear=clear,
        noisy=noisy,
        clear_alone=speech_alone(clear),
        noisy_alone=speech_alone(noisy),
        noisy_audio=f"data:audio/wav;base64,{base64.b64encode(noisy_bytes).decode()}",
        noisy_score=noisy_score,
        facts=facts,
    )
