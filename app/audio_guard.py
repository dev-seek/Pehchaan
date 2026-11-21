"""Check uploaded audio before it can cost money: right type, small enough, really audio, and short enough."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from pehchaan.config import settings

AUDIO_EXTENSIONS = {".flac", ".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".ogg", ".wav", ".webm"}
_CHECK_RATE = 8000  # decoded to 16-bit mono at this rate only to count the seconds


def audio_seconds(content: bytes, extension: str) -> float:
    """Decode rather than read the header: browser recordings often carry no duration, and headers can lie."""
    limit = settings()["api"]["max_audio_seconds"]
    with tempfile.NamedTemporaryFile(suffix=extension) as file:
        file.write(content)
        file.flush()
        command = [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-i",
            file.name,
            "-map",
            "0:a:0",
            "-t",
            str(limit + 1),
            "-ac",
            "1",
            "-ar",
            str(_CHECK_RATE),
            "-f",
            "s16le",
            "pipe:1",
        ]
        try:
            done = subprocess.run(command, capture_output=True, timeout=settings()["api"]["audio_check_timeout_s"])
        except FileNotFoundError as exc:
            raise HTTPException(503, "Audio checking is not available on this server.") from exc
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(400, "This audio could not be read.") from exc
    if done.returncode != 0 or not done.stdout:
        raise HTTPException(400, "This file is not readable audio.")
    return len(done.stdout) / (2 * _CHECK_RATE)


def check_audio(content: bytes, extension: str) -> float:
    cfg = settings()["api"]
    if extension not in AUDIO_EXTENSIONS:
        raise HTTPException(400, "Unsupported audio file type.")
    if not content:
        raise HTTPException(400, "Audio is empty.")
    if len(content) > cfg["max_audio_bytes"]:
        raise HTTPException(413, f"Audio is larger than {cfg['max_audio_bytes'] // (1024 * 1024)} MB.")
    seconds = audio_seconds(content, extension)
    if seconds > cfg["max_audio_seconds"]:
        raise HTTPException(413, f"Audio is longer than {cfg['max_audio_seconds']} seconds.")
    return seconds


async def read_upload(upload: UploadFile) -> tuple[bytes, str]:
    try:
        extension = Path(upload.filename or "call.wav").suffix.lower()
        content = await upload.read(settings()["api"]["max_audio_bytes"] + 1)
    finally:
        await upload.close()
    return content, extension
