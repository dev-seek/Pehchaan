"""Replay labelled audio at playback speed through one realtime transcription session."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import subprocess
from pathlib import Path
from time import perf_counter

from jiwer import wer

from pehchaan.config import load_dotenv
from pehchaan_live.settings import live_settings

from .speech import _clip_rows, normalize

ENDPOINT = "wss://api.openai.com/v1/realtime?intent=transcription"
RATE = 24000
CHUNK_BYTES = 4800


async def _send(socket, event_type: str, **fields):
    await socket.send(json.dumps({"type": event_type, **fields}))


async def _wait(socket, event_type: str, item_id: str | None = None):
    while True:
        event = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
        if event["type"] == "error":
            raise RuntimeError(f"realtime transcription request refused ({event['error'].get('code')})")
        if (event["type"] == "conversation.item.input_audio_transcription.failed"
                and event.get("item_id") == item_id):
            raise RuntimeError("transcription failed for a committed turn")
        if event["type"] == event_type and (item_id is None or event.get("item_id") == item_id):
            return event


def _pcm(audio: Path) -> bytes:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(audio), "-vn",
         "-ac", "1", "-ar", str(RATE), "-f", "s16le", "pipe:1"],
        capture_output=True, check=True, timeout=15,
    )
    if not RATE // 5 * 2 <= len(result.stdout) <= RATE * 2 * 30:
        raise ValueError("stream smoke accepts turns between 200 ms and 30 seconds")
    return result.stdout


async def stream(manifest: Path, limit: int) -> dict:
    from websockets.asyncio.client import connect

    config = live_settings()["benchmark"]
    load_dotenv()
    rows = [(clip, _pcm(audio)) for clip, audio in _clip_rows(manifest, limit)]
    settings = {"type": "transcription", "audio": {"input": {
        "format": {"type": "audio/pcm", "rate": RATE}, "transcription": {"model": config["openai_stream_model"]},
        "turn_detection": None,
    }}}
    records = []
    async with connect(ENDPOINT, additional_headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]}) as socket:
        await _send(socket, "session.update", session=settings)
        await _wait(socket, "session.updated")
        for clip, pcm in rows:
            started = perf_counter()
            for offset in range(0, len(pcm), CHUNK_BYTES):
                chunk = pcm[offset: offset + CHUNK_BYTES]
                await _send(socket, "input_audio_buffer.append", audio=base64.b64encode(chunk).decode("ascii"))
                await asyncio.sleep(max(0, started + (offset + len(chunk)) / (RATE * 2) - perf_counter()))
            committed = perf_counter()
            await _send(socket, "input_audio_buffer.commit")
            item = await _wait(socket, "input_audio_buffer.committed")
            final = await _wait(socket, "conversation.item.input_audio_transcription.completed", item["item_id"])
            elapsed = (perf_counter() - committed) * 1000
            records.append({"sample": clip.id, "audio_sha256": clip.sha256, "dataset_revision": clip.revision,
                            "line": clip.condition, "language": clip.language, "transcript": final["transcript"],
                            "commit_to_final_ms": elapsed, "word_error_rate": wer(normalize(clip.transcript),
                                                                                 normalize(final["transcript"]))})
    return {"request": settings, "records": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--limit", type=int, default=2, choices=range(1, 7), metavar="1–6")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = asyncio.run(stream(args.manifest, args.limit))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Streamed {len(result['records'])} caller turns. Wrote {args.out}")


if __name__ == "__main__":
    main()
