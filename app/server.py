"""
Pehchaan app server (FastAPI).

  uvicorn app.server:app --reload --port 8000
  open http://localhost:8000          -> demo (Live + Bench tabs)
  open http://localhost:8000/record   -> record your locked real test set (one script at a time)

API contract: docs/API.md
"""

from __future__ import annotations

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bench.learning import LearningLoop
from pehchaan import CallContext, process
from pehchaan.asr import transcribe
from pehchaan.config import ROOT, path, settings
from pehchaan.pipeline import default_memory_store

from .access import is_public, local_only, passcode, require_live
from .demo_api import router as demo_router
from .studio import router as studio_router

app = FastAPI(title="Pehchaan", version="0.1")
app.include_router(demo_router)
app.include_router(studio_router)
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
UPLOADS = ROOT / settings()["paths"]["cache"] / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
DEMO_CTX = ROOT / "data" / "demo" / "contexts"
_pool = ThreadPoolExecutor(max_workers=4)
_memory = default_memory_store()
_learning = LearningLoop(_memory, ROOT / settings()["learning"]["api_ledger_db"])
PUBLISHED = ROOT / "data" / "published"
BENCH_SETS = ("dev", "test_real_phone")
RECORD_SPLITS = ("test",)
_AUDIO_SUFFIXES = {".webm", ".ogg", ".m4a", ".mp4", ".wav"}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/record", dependencies=[Depends(local_only)])
def record_page():
    return FileResponse(STATIC / "record.html")


@app.get("/api/health")
def health():
    return {"ok": True, "models": settings()["models"]}


@app.get("/api/config")
def site_config():
    public = is_public()
    return {"mode": "public" if public else "local", "live_needs_passcode": public,
            "live_available": not public or bool(passcode()), "studio": not public}


# ---- recording the locked real test set --------------------------------------------------------
@app.get("/api/scripts", dependencies=[Depends(local_only)])
def scripts(split: str = "test"):
    if split not in RECORD_SPLITS:
        raise HTTPException(400, "unknown split")
    f = path("bench") / f"{split}_scripts.jsonl"
    if not f.exists():
        raise HTTPException(404, "run: python -m bench.generate")
    rec_dir = path("audio") / f"{split}_real"
    done = {p.stem.split("__")[0] for p in rec_dir.glob("*.*")} if rec_dir.exists() else set()
    rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [{"script_id": r["script_id"], "lang": r["lang"], "domain": r["domain"], "spoken": r["spoken"],
             "recorded": r["script_id"] in done} for r in rows]


@app.post("/api/record", dependencies=[Depends(local_only)])
async def record(script_id: str = Form(...), split: str = Form("test"), audio: UploadFile = File(...)):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", script_id) or split not in RECORD_SPLITS:
        raise HTTPException(400, "bad id")
    rec_dir = path("audio") / f"{split}_real"
    rec_dir.mkdir(parents=True, exist_ok=True)
    for old in rec_dir.glob(f"{script_id}.*"):
        old.unlink()
    ext = Path(audio.filename or "a.webm").suffix.lower() or ".webm"
    if ext not in _AUDIO_SUFFIXES:
        raise HTTPException(400, "unsupported audio type")
    content = await audio.read(settings()["demo"]["max_recording_bytes"] + 1)
    if not content or len(content) > settings()["demo"]["max_recording_bytes"]:
        raise HTTPException(413, "recording is empty or too large")
    out = rec_dir / f"{script_id}{ext}"
    out.write_bytes(content)
    return {"saved": str(out.relative_to(ROOT)), "bytes": out.stat().st_size}


# ---- live processing ---------------------------------------------------------------------------
@app.get("/api/demo/contexts")
def demo_contexts():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(DEMO_CTX.glob("*.json"))}


@app.post("/api/process", dependencies=[Depends(require_live)])
@app.post("/v1/pehchaan/transcribe", dependencies=[Depends(require_live)])
async def api_process(
    audio: UploadFile | None = File(None),
    text: str | None = Form(None),
    context: str | None = Form(None),
    level: str = Form("C3"),
    user_id: str | None = Form(None),
):
    cfg = settings()
    try:
        raw_ctx = json.loads(context) if context else {}
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"context is not valid JSON: {e}") from e
    if not isinstance(raw_ctx, dict):
        raise HTTPException(400, "context must be a JSON object")
    if level not in ("C0", "C1", "C2", "C3", "C4"):
        raise HTTPException(400, f"unknown level {level}")
    if user_id:
        raw_ctx.setdefault("user", {})["id"] = user_id
    ctx = CallContext.build(raw_ctx, level)
    baseline, tokens, src_text, second_opinion = None, None, text, None
    if audio is not None:
        with TemporaryDirectory(dir=UPLOADS) as temp:
            ext = Path(audio.filename or "call.webm").suffix or ".webm"
            f = Path(temp) / f"call{ext}"
            try:
                f.write_bytes(await audio.read())
            finally:
                await audio.close()
            m = cfg["models"]
            keywords = ctx.keyword_list(cfg["asr"]["keywords_max"])
            lang = cfg["asr"]["languages"]
            fut_plain = _pool.submit(transcribe, f, m["asr_plain"], languages=lang)
            fut_main = _pool.submit(transcribe, f, m["asr_keywords"], keywords=keywords, languages=lang)
            plain, main = await asyncio.gather(
                asyncio.wrap_future(fut_plain), asyncio.wrap_future(fut_main), return_exceptions=True
            )
            if isinstance(plain, BaseException):
                raise plain
            if isinstance(main, BaseException):
                raise main
        baseline = {"text": plain["text"], "model": plain["model"], "latency_ms": plain["latency_ms"]}
        src_text, tokens = main["text"], main["tokens"]
        second_opinion = plain["text"] if keywords else None  # context-free evidence (DECISIONS D-022)
        asr_info = {"text": main["text"], "model": main["model"], "latency_ms": main["latency_ms"]}
    else:
        if not text:
            raise HTTPException(400, "send audio or text")
        asr_info = {"text": text, "model": "typed", "latency_ms": 0}
    r = process(src_text, ctx, asr_pieces=tokens, memory=_memory, second_opinion=second_opinion)
    return JSONResponse({"baseline": baseline, "asr": asr_info, "pehchaan": r.to_dict(), "level": level})


class Confirm(BaseModel):
    user_id: str
    heard: str
    canonical: str
    etype: str


@app.post("/api/memory/confirm", dependencies=[Depends(local_only)])
def memory_confirm(c: Confirm):
    """A correction only becomes automatic through the learning gate (bench/learning.py, D-027)."""
    if c.etype not in settings()["learning"]["learnable_types"]:
        raise HTTPException(400, f"{c.etype} cannot be learned: numbers are read-only (D-021)")
    return _learning.propose(c.user_id, c.heard, c.canonical, c.etype)


@app.get("/api/memory/{user_id}", dependencies=[Depends(local_only)])
def memory_get(user_id: str):
    return _memory.load(user_id)


@app.delete("/api/memory/{user_id}", dependencies=[Depends(local_only)])
def memory_reset(user_id: str):
    _memory.forget(user_id)
    return {"reset": True}


# ---- measured results for the site -------------------------------------------------------------
@app.get("/api/bench/latest")
def bench_latest(clips: str = "dev"):
    """The newest local run if there is one, otherwise the snapshot published in git."""
    if clips not in BENCH_SETS:
        raise HTTPException(404, "unknown result set")
    local = ROOT / settings()["paths"]["results"] / f"latest_{clips}.json"
    file = local if local.exists() else PUBLISHED / f"benchmark_{clips}.json"
    if not file.exists():
        raise HTTPException(404, f"no results yet: python -m bench.run --clips {clips}")
    report = json.loads(file.read_text(encoding="utf-8"))
    report.pop("dir", None)
    return report


@app.get("/api/bench/available")
def bench_available():
    roots = (ROOT / settings()["paths"]["results"], PUBLISHED)
    return [c for c in BENCH_SETS if any((d / n).exists() for d in roots for n in (f"latest_{c}.json", f"benchmark_{c}.json"))]


@app.get("/api/learning/proof")
def learning_proof():
    file = PUBLISHED / "learning_dev.json"
    if not file.exists():
        raise HTTPException(404, "run: python -m bench.learning_proof")
    return json.loads(file.read_text(encoding="utf-8"))
