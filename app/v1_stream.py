"""
WS /v1/stream: phrase-by-phrase verification while a call is happening.

The first message is JSON and carries the credential, because browsers cannot set WebSocket headers:
    {"type": "start", "mode": "audio" | "transcript", "auth": {"passcode": "..."} | {"openai_key": "..."}, "context": {...}}
Then send 16 kHz mono 16-bit PCM as binary frames, or {"type": "transcript", "text": "...", "is_final": true}.
End with {"type": "stop"}. Facts are sent when a phrase is final, so a verdict is never based on half a sentence.
The closing message re-checks the whole call, so a number split across two phrases is still read as one number.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from pehchaan.config import settings
from pehchaan_sdk import AudioFile, CustomTranscriptProvider, VerifyResult

from .access import Credential, authenticate, spend
from .call_log import record_call
from .segmenter import Segmenter, to_wav
from .v1 import clean_language, engine_for, parse_context, speech_provider, upstream_error

router = APIRouter()
_CLOSE = {401: 4401, 403: 4403, 408: 4408, 413: 4413, 429: 4429}
_open = {"n": 0}


class _End(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


class Session:
    def __init__(self, ws: WebSocket, credential: Credential, start: dict):
        self.ws, self.credential, self.cfg = ws, credential, settings()["api"]["stream"]
        self.mode = start.get("mode", "transcript")
        if self.mode not in ("audio", "transcript"):
            raise _End(400, "mode must be audio or transcript")
        self.raw_context = start.get("context")
        self.context = parse_context(self.raw_context, credential)
        self.language = clean_language(start.get("language") if isinstance(start.get("language"), str) else None)
        provider = (
            speech_provider(start.get("model"), credential) if self.mode == "audio" else CustomTranscriptProvider()
        )
        self.engine = engine_for(provider, credential)
        self.seen: set[tuple] = set()
        self.raw, self.alt = [], []
        self.bytes_in = self.count = 0
        self.jobs: asyncio.Queue = asyncio.Queue()
        self.segmenter = Segmenter(
            self.cfg["sample_rate"],
            pause_ms=self.cfg["pause_ms"],
            min_s=self.cfg["min_phrase_s"],
            max_s=self.cfg["max_phrase_s"],
            min_level=self.cfg["min_level"],
            over_floor=self.cfg["over_floor"],
        )

    async def send_result(self, result: VerifyResult) -> None:
        self.count += 1
        await self.ws.send_json(
            {
                "type": "phrase",
                "phrase": self.count,
                "text": result.verified_text,
                "raw_text": result.raw_text,
                "stt_ms": result.telemetry.stt_ms,
                "harness_ms": result.telemetry.harness_ms,
            }
        )
        for fact in result.entities:
            mark = (fact.type, fact.heard, fact.value, fact.status)
            if mark not in self.seen:
                self.seen.add(mark)
                await self.ws.send_json({"type": "fact", "phrase": self.count, "fact": fact.model_dump()})
        if result.clarifier_prompt:
            await self.ws.send_json({"type": "clarifier", "phrase": self.count, "prompt": result.clarifier_prompt})

    async def audio_phrase(self, pcm: bytes) -> None:
        spend(self.ws, self.credential)  # every phrase is a paid transcription
        audio = AudioFile("phrase.wav", to_wav(pcm, self.cfg["sample_rate"]))
        result = await run_in_threadpool(self.engine.verify_audio, audio, self.context, language=self.language)
        self.raw.append(result.raw_text)
        if result.alt_text:
            self.alt.append(result.alt_text)
        await self.send_result(result)

    async def text_phrase(self, text: str, alt: str | None) -> None:
        result = await run_in_threadpool(
            self.engine.verify_transcript, text, self.context, alt, language=self.language
        )
        self.raw.append(text)
        if alt:
            self.alt.append(alt)
        await self.send_result(result)

    async def worker(self) -> None:
        while True:
            job = await self.jobs.get()
            if job is None:
                return
            kind, *args = job
            await (self.audio_phrase(*args) if kind == "audio" else self.text_phrase(*args))

    def on_audio(self, chunk: bytes) -> None:
        if self.mode != "audio":
            raise _End(400, "this session expects transcript messages")
        self.bytes_in += len(chunk)
        if self.bytes_in > self.cfg["max_audio_seconds"] * self.cfg["sample_rate"] * 2:
            raise _End(413, f"Live audio is limited to {self.cfg['max_audio_seconds']} seconds.")
        for phrase in self.segmenter.feed(chunk):
            self.jobs.put_nowait(("audio", phrase))

    def on_text(self, message: dict) -> None:
        if self.mode != "transcript":
            raise _End(400, "this session expects binary audio")
        text = str(message.get("text", "")).strip()
        self.bytes_in += len(text)
        if self.bytes_in > settings()["demo"]["max_text_chars"]:
            raise _End(413, "This transcript is too long.")
        if text and message.get("is_final"):
            alt = message.get("alt_text")
            self.jobs.put_nowait(("text", text, str(alt) if alt else None))

    async def finish(self) -> None:
        if self.mode == "audio":
            last = self.segmenter.flush()
            if last:
                self.jobs.put_nowait(("audio", last))
        self.jobs.put_nowait(None)

    async def closing_result(self) -> None:
        if not self.raw:
            await self.ws.send_json({"type": "final", "result": None})
            return
        joined_alt = " ".join(self.alt) if len(self.alt) == len(self.raw) else None
        result = await run_in_threadpool(
            self.engine.verify_transcript,
            " ".join(self.raw),
            self.context,
            joined_alt,
            model=getattr(self.engine.provider, "model", "external"),
            language=self.language,
        )
        result = await run_in_threadpool(
            record_call, self.credential.tenant, self.raw_context, self.context, result, "stream", self.language
        )
        await self.ws.send_json({"type": "final", "result": result.model_dump()})

    async def run(self) -> None:
        deadline = time.monotonic() + self.cfg["max_session_s"]
        worker = asyncio.create_task(self.worker())
        try:
            while True:
                if worker.done():
                    worker.result()
                left = min(self.cfg["idle_timeout_s"], deadline - time.monotonic())
                if left <= 0:
                    raise _End(408, "This live session reached its time limit.")
                try:
                    message = await asyncio.wait_for(self.ws.receive(), left)
                except asyncio.TimeoutError as exc:
                    raise _End(408, "No data arrived, so the session was closed.") from exc
                if message["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(message.get("code", 1000))
                if message.get("bytes") is not None:
                    self.on_audio(message["bytes"])
                    continue
                data = _json(message.get("text"))
                if data.get("type") == "stop":
                    break
                if data.get("type") != "transcript":
                    raise _End(400, "unknown message type")
                self.on_text(data)
            await self.finish()
            await asyncio.wait_for(worker, self.cfg["finish_timeout_s"])
            await self.closing_result()
        finally:
            worker.cancel()


def _json(text: str | None) -> dict:
    try:
        data = json.loads(text or "")
    except ValueError as exc:
        raise _End(400, "messages must be JSON or binary audio") from exc
    if not isinstance(data, dict):
        raise _End(400, "messages must be JSON objects")
    return data


async def _begin(ws: WebSocket) -> Session:
    cfg = settings()["api"]["stream"]
    try:
        first = await asyncio.wait_for(ws.receive(), cfg["start_timeout_s"])
    except asyncio.TimeoutError as exc:
        raise _End(408, "Send a start message first.") from exc
    if first["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(first.get("code", 1000))
    start = _json(first.get("text"))
    if start.get("type") != "start":
        raise _End(400, "The first message must be a start message.")
    auth = start.get("auth") if isinstance(start.get("auth"), dict) else {}
    credential = authenticate(
        ws,
        demo_passcode=auth.get("passcode") or ws.headers.get("x-demo-passcode"),
        openai_key=auth.get("openai_key") or ws.headers.get("x-openai-key"),
        authorization=ws.headers.get("authorization"),
    )
    session = Session(ws, credential, start)
    if session.mode == "transcript":
        spend(ws, credential)  # audio is charged per phrase instead
    return session


@router.websocket("/v1/stream")
async def stream(ws: WebSocket) -> None:
    await ws.accept()
    if _open["n"] >= settings()["api"]["stream"]["max_open"]:
        await _fail(ws, 429, "The live service is busy. Try again in a moment.")
        return
    _open["n"] += 1
    try:
        session = await _begin(ws)
        limits = {k: session.cfg[k] for k in ("sample_rate", "max_audio_seconds", "max_session_s")}
        await ws.send_json({"type": "ready", "mode": session.mode, "limits": limits})
        await session.run()
        await ws.close()
    except WebSocketDisconnect:
        pass
    except _End as end:
        await _fail(ws, end.status, end.message)
    except HTTPException as exc:
        await _fail(ws, exc.status_code, str(exc.detail))
    except TimeoutError:
        await _fail(ws, 408, "The speech model took too long.")
    except Exception as exc:  # noqa: BLE001
        mapped = upstream_error(exc)
        await _fail(ws, mapped.status_code, str(mapped.detail))
    finally:
        _open["n"] -= 1


async def _fail(ws: WebSocket, status: int, message: str) -> None:
    try:
        await ws.send_json({"type": "error", "status": status, "message": message})
        await ws.close(code=_CLOSE.get(status, 4400))
    except (RuntimeError, WebSocketDisconnect):
        pass
