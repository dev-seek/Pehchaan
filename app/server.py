"""
Pehchaan app server (FastAPI).

  uvicorn app.server:app --reload --port 8000
  open http://localhost:8000          -> demo (Live + Bench tabs)
  open http://localhost:8000/record   -> record your locked real test set (one script at a time)

API contract: docs/API.md
"""
from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pehchaan import CallContext, process
from pehchaan.asr import transcribe
from pehchaan.config import ROOT, path, settings
from pehchaan.pipeline import default_memory_store

app = FastAPI(title="Pehchaan", version="0.1")
STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
UPLOADS = ROOT / settings()["paths"]["cache"] / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
DEMO_CTX = ROOT / "data" / "demo" / "contexts"
_pool = ThreadPoolExecutor(max_workers=4)
_memory = default_memory_store()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/record")
def record_page():
    return FileResponse(STATIC / "record.html")


@app.get("/api/health")
def health():
    return {"ok": True, "models": settings()["models"]}


# ---- recording the locked real test set --------------------------------------------------------
@app.get("/api/scripts")
def scripts(split: str = "test"):
    f = path("bench") / f"{split}_scripts.jsonl"
    if not f.exists():
        raise HTTPException(404, "run: python -m bench.generate")
    rec_dir = path("audio") / f"{split}_real"
    done = {p.stem.split("__")[0] for p in rec_dir.glob("*.*")} if rec_dir.exists() else set()
    rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [{"script_id": r["script_id"], "lang": r["lang"], "domain": r["domain"], "spoken": r["spoken"],
             "recorded": r["script_id"] in done} for r in rows]


@app.post("/api/record")
async def record(script_id: str = Form(...), split: str = Form("test"), audio: UploadFile = File(...)):
    if "/" in script_id or ".." in script_id:
        raise HTTPException(400, "bad id")
    rec_dir = path("audio") / f"{split}_real"
    rec_dir.mkdir(parents=True, exist_ok=True)
    for old in rec_dir.glob(f"{script_id}.*"):
        old.unlink()
    ext = Path(audio.filename or "a.webm").suffix or ".webm"
    out = rec_dir / f"{script_id}{ext}"
    out.write_bytes(await audio.read())
    return {"saved": str(out.relative_to(ROOT)), "bytes": out.stat().st_size}


# ---- live processing ---------------------------------------------------------------------------
@app.get("/api/demo/contexts")
def demo_contexts():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(DEMO_CTX.glob("*.json"))}


@app.post("/api/process")
async def api_process(audio: UploadFile | None = File(None), text: str | None = Form(None),
                      context: str | None = Form(None), level: str = Form("C3"),
                      user_id: str | None = Form(None)):
    cfg = settings()
    try:
        raw_ctx = json.loads(context) if context else {}
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"context is not valid JSON: {e}") from e
    if level not in ("C0", "C1", "C2", "C3", "C4"):
        raise HTTPException(400, f"unknown level {level}")
    if user_id:
        raw_ctx.setdefault("user", {})["id"] = user_id
    ctx = CallContext.build(raw_ctx, level)
    baseline, tokens, src_text, second_opinion = None, None, text, None
    if audio is not None:
        f = UPLOADS / f"{uuid.uuid4().hex}{Path(audio.filename or 'a.webm').suffix or '.webm'}"
        f.write_bytes(await audio.read())
        m = cfg["models"]
        keywords = ctx.keyword_list(cfg["asr"]["keywords_max"])
        fut_plain = _pool.submit(transcribe, f, m["asr_plain"], languages=cfg["asr"]["languages"])
        fut_main = _pool.submit(transcribe, f, m["asr_keywords"], keywords=keywords, languages=cfg["asr"]["languages"])
        plain, main = fut_plain.result(), fut_main.result()
        baseline = {"text": plain["text"], "model": plain["model"], "latency_ms": plain["latency_ms"]}
        src_text, tokens = main["text"], main["tokens"]
        second_opinion = plain["text"] if keywords else None    # context-free evidence (DECISIONS D-022)
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


@app.post("/api/memory/confirm")
def memory_confirm(c: Confirm):
    try:
        return _memory.remember(c.user_id, c.heard, c.canonical, c.etype)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/memory/{user_id}")
def memory_get(user_id: str):
    return _memory.load(user_id)


@app.delete("/api/memory/{user_id}")
def memory_reset(user_id: str):
    _memory.forget(user_id)
    return {"reset": True}


# ---- benchmark results for the Bench tab -------------------------------------------------------
@app.get("/api/bench/latest")
def bench_latest(clips: str = "dev"):
    f = ROOT / settings()["paths"]["results"] / f"latest_{clips}.json"
    if not f.exists():
        raise HTTPException(404, f"no results yet: python -m bench.run --clips {clips}")
    return json.loads(f.read_text(encoding="utf-8"))


@app.get("/api/bench/available")
def bench_available():
    d = ROOT / settings()["paths"]["results"]
    return sorted(p.stem.replace("latest_", "") for p in d.glob("latest_*.json")) if d.exists() else []
