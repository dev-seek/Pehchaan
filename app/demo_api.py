"""HTTP routes for the local live comparison and explicit corrections."""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ValidationError

from pehchaan.config import ROOT, settings

from .demo_compare import replay, run_compare, systems
from .demo_presets import catalog, preset_audio, public_preset
from .demo_state import MEMORY_TYPES, DemoMemory, DemoRun, DemoRuns

router = APIRouter(prefix="/api/demo")
_session_cookie = "pehchaan_demo_session"
_runs = DemoRuns()
_memory = DemoMemory(ROOT / settings()["demo"]["memory_db"])
_active: set[asyncio.Task] = set()
_AUDIO_EXTENSIONS = {".flac", ".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".ogg", ".wav", ".webm"}


class _User(BaseModel):
    city: str | None = None


class _Caller(BaseModel):
    number: str | None = None
    cnap_name: str | None = None


class _Contact(BaseModel):
    name: str | None = None
    number: str | None = None


class _Message(BaseModel):
    sender: str = ""
    body: str = ""


class _Context(BaseModel):
    user: _User | None = None
    caller: _Caller | None = None
    contacts: list[_Contact] | None = None
    sms: list[_Message] | None = None
    places: list[str] | None = None
    domain: str | None = None


class _Replay(BaseModel):
    system_id: str


class _Confirm(_Replay):
    entity_id: str
    canonical: str


def parse_context(value: str | None, default: dict, field: str) -> dict:
    if value is None:
        return default
    if len(value) > settings()["demo"]["max_context_chars"]:
        raise HTTPException(413, f"{field} is too large")
    try:
        return _Context.model_validate_json(value).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise HTTPException(400, f"{field} must be a valid call context JSON object") from exc


async def read_audio(upload: UploadFile) -> tuple[bytes, str]:
    limit = settings()["demo"]["max_audio_bytes"]
    try:
        extension = Path(upload.filename or "call.webm").suffix.lower()
        if extension not in _AUDIO_EXTENSIONS:
            raise HTTPException(400, "Unsupported audio file type")
        content = await upload.read(limit + 1)
    finally:
        await upload.close()
    if not content:
        raise HTTPException(400, "Audio is empty")
    if len(content) > limit:
        raise HTTPException(413, "Audio is too large")
    return content, extension


@router.get("/presets")
def list_presets():
    return [public_preset(preset) for preset in catalog().values() if preset_audio(preset)]


def find_preset(preset_id: str) -> tuple[dict, Path]:
    preset = catalog().get(preset_id)
    file = preset_audio(preset) if preset else None
    if not file:
        raise HTTPException(404, "Demo preset unavailable")
    return preset, file


@router.get("/presets/{preset_id}/audio")
def get_preset_audio(preset_id: str):
    return FileResponse(find_preset(preset_id)[1])


@router.post("/compare")
async def compare(request: Request, audio: Annotated[UploadFile | None, File()] = None,
                  text: Annotated[str | None, Form()] = None, preset: Annotated[str | None, Form()] = None,
                  context: Annotated[str | None, Form()] = None, context_adv: Annotated[str | None, Form()] = None,
                  session: Annotated[str | None, Cookie(alias=_session_cookie)] = None):
    if sum(value is not None for value in (audio, preset, text)) != 1:
        raise HTTPException(400, "Send exactly one of audio, preset or text")
    cfg = settings()["demo"]
    if text is not None and (not text.strip() or len(text) > cfg["max_text_chars"]):
        raise HTTPException(400, f"Enter a transcript up to {cfg['max_text_chars']} characters")
    entry, file = find_preset(preset) if preset else ({}, None)
    raw = {"context": parse_context(context, entry.get("context", {}), "context"),
           "context_adv": parse_context(context_adv, entry.get("context_adv", {}), "context_adv")}
    upload = await read_audio(audio) if audio else None
    if len(_active) >= cfg["max_active_runs"]:
        raise HTTPException(429, "The comparison queue is full. Try again when a run finishes.")
    known_session = session and re.fullmatch(r"[a-f0-9]{32}", session)
    session = session if known_session else uuid.uuid4().hex
    run_id = uuid.uuid4().hex
    truth = entry if "reference" in entry and "entities" in entry else None
    run = DemoRun(session, raw, truth)
    _runs.save(run_id, run)
    asyncio.get_running_loop().call_later(cfg["run_ttl_s"], _runs.expire, run_id)
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_compare(run_id, run, queue, _memory, audio=file, upload=upload, text=text,
                                          cache_answers=bool(entry and context is None and context_adv is None)))
    _active.add(task)
    task.add_done_callback(_active.discard)
    started = {"event": "started", "run_id": run_id, "main_system": settings()["bench"]["main_system"],
               "systems": [{k: v for k, v in s.items() if k in {"id", "kind", "level"}} for s in systems().values()],
               "mode": "preset" if preset else "audio" if upload else "text"}
    if preset:
        started["preset"] = preset
    response = StreamingResponse(events(started, queue), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    if not known_session:
        response.set_cookie(_session_cookie, session, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https")
    return response


def _ndjson(message: dict) -> str:
    return json.dumps(message, ensure_ascii=False) + "\n"


async def events(started: dict, queue: asyncio.Queue):
    yield _ndjson(started)
    while True:
        message = await queue.get()
        yield _ndjson(message)
        if message["event"] == "done":
            break


def _saved(run_id: str, system_id: str, session: str | None) -> tuple[DemoRun, dict]:
    run = _runs.find(run_id, session)
    if run is None:
        raise HTTPException(404, "Demo run is unavailable or expired")
    system = systems().get(system_id)
    if not system or system["kind"] != "pehchaan" or system_id not in run.results:
        raise HTTPException(404, "Pehchaan result unavailable for this run")
    return run, system


@router.post("/{run_id}/confirm")
def confirm(run_id: str, payload: _Confirm, session: Annotated[str | None, Cookie(alias=_session_cookie)] = None):
    run, _ = _saved(run_id, payload.system_id, session)
    entities = run.results[payload.system_id]["entities"]
    entity = next((e for e in entities if e["id"] == payload.entity_id), None)
    if not entity:
        raise HTTPException(404, "Entity unavailable for this run")
    if entity["status"] != "FLAGGED" or entity["etype"] not in MEMORY_TYPES:
        raise HTTPException(400, "Only flagged names and places can be remembered")
    canonical = payload.canonical.strip()
    if len(canonical) > settings()["demo"]["max_confirmation_chars"]:
        raise HTTPException(400, "Name or place is too long")
    try:
        return _memory.remember(run.session, entity["surface"], canonical, entity["etype"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{run_id}/replay")
async def replay_result(run_id: str, payload: _Replay,
                        session: Annotated[str | None, Cookie(alias=_session_cookie)] = None):
    run, system = _saved(run_id, payload.system_id, session)
    return await replay(run, system, _memory)
