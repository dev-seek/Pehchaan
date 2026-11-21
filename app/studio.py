"""Voice studio (laptop only): record real-voice sample calls for the public site. Never touches the locked exam."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from pehchaan.config import ROOT, settings

from .access import local_only
from .demo_presets import real_samples

router = APIRouter(dependencies=[Depends(local_only)])
_STATIC = Path(__file__).parent / "static"
_SUFFIXES = {".webm", ".ogg", ".m4a", ".mp4", ".wav"}


@router.get("/studio")
def studio_page():
    return FileResponse(_STATIC / "studio.html")


@router.get("/api/studio/samples")
def list_samples():
    return [{"id": s["id"], "label": s["label"], "language": s["language"], "spoken": s["spoken"],
             "tip": s.get("tip", ""), "recorded": (ROOT / s["audio"]).is_file()} for s in real_samples()]


def _to_wav(source: Path, target: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise HTTPException(500, "ffmpeg is needed to save a sample")
    done = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-ac", "1", "-ar", "16000", str(target)],
                          capture_output=True, timeout=60, check=False)
    if done.returncode or not target.is_file():
        raise HTTPException(400, "could not read this recording")


@router.post("/api/studio/samples/{sample_id}")
async def save_sample(sample_id: str, audio: Annotated[UploadFile, File()]):
    sample = next((s for s in real_samples() if s["id"] == sample_id), None)
    if sample is None or not re.fullmatch(r"[a-z0-9-]+", sample_id):
        raise HTTPException(404, "unknown sample")
    suffix = Path(audio.filename or "take.webm").suffix.lower()
    if suffix not in _SUFFIXES:
        raise HTTPException(400, "unsupported audio type")
    limit = settings()["demo"]["max_recording_bytes"]
    content = await audio.read(limit + 1)
    if not content or len(content) > limit:
        raise HTTPException(413, "recording is empty or too large")
    target = ROOT / sample["audio"]
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as temp:
        take = Path(temp) / f"take{suffix}"
        take.write_bytes(content)
        converted = Path(temp) / "take.wav"
        _to_wav(take, converted)
        shutil.move(str(converted), target)
    return {"saved": sample_id, "bytes": target.stat().st_size}


@router.delete("/api/studio/samples/{sample_id}")
def delete_sample(sample_id: str):
    sample = next((s for s in real_samples() if s["id"] == sample_id), None)
    if sample is None:
        raise HTTPException(404, "unknown sample")
    (ROOT / sample["audio"]).unlink(missing_ok=True)
    return {"deleted": sample_id}
