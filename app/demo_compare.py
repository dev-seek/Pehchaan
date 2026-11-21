"""Coordinate one comparison across configured systems, sharing identical ASR requests."""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

from bench.systems import asr_request, context_at, execute_system, needed_transcripts, primary_key
from pehchaan.config import path, settings

from .demo_results import serialize_result
from .demo_state import DemoMemory, DemoRun

_logger = logging.getLogger(__name__)
_workers = ThreadPoolExecutor(max_workers=settings()["asr"]["max_workers"])


def systems() -> dict[str, dict]:
    return {s["id"]: s for s in settings()["bench"]["systems"]}


async def _worker(function, /, *args, **kwargs):
    return await asyncio.get_running_loop().run_in_executor(_workers, partial(function, *args, **kwargs))


def run_system(system: dict, run: DemoRun, source: dict, second: dict | None, memory: DemoMemory,
               *, replay: bool = False, cache_answers: bool = False) -> dict:
    ctx = context_at(run.contexts, system.get("level", system.get("keywords_level", "C3")))
    ctx.user_id = run.session
    output = execute_system(system, source, ctx, second_opinion=second, memory=memory,
                            use_judge=settings()["verifier"]["enabled"] and not replay, cache_answers=cache_answers)
    return serialize_result(output, ctx, source, second, run.truth)


def _prepare_inputs(run: DemoRun, configured: dict[str, dict], *, audio: Path | None, text: str | None,
                    cache_answers: bool) -> dict:
    keys = needed_transcripts(list(configured.values()))
    if audio is None:
        ready = asyncio.get_running_loop().create_future()
        ready.set_result({"text": text, "tokens": [], "model": "typed", "latency_ms": 0, "cached": False})
        return dict.fromkeys(keys, ready)

    plans = {key: asr_request(run.contexts, key) for key in sorted(keys)}
    tasks = {request: asyncio.create_task(_worker(request.run, audio, cache_answers=cache_answers))
             for request in dict.fromkeys(plans.values())}
    return {key: tasks[request] for key, request in plans.items()}


async def _dispatch(run: DemoRun, queue: asyncio.Queue, memory: DemoMemory, *, audio: Path | None,
                    text: str | None, cache_answers: bool) -> None:
    configured = systems()
    inputs = _prepare_inputs(run, configured, audio=audio, text=text, cache_answers=cache_answers)
    work = {}

    async def compare(system: dict):
        sid = system["id"]
        try:
            key = primary_key(system, configured)
            if key in inputs:
                source = await inputs[key]
            else:
                previous = await work[key]
                if previous is None:
                    raise RuntimeError("source system failed")
                source = {"text": previous["text"], "tokens": []}
            second = await inputs[system["second_opinion"]] if audio and system.get("second_opinion") else None
            result = await _worker(run_system, system, run, source, second, memory, cache_answers=cache_answers)
        except Exception as exc:
            _logger.warning("Demo approach %s failed (%s)", sid, type(exc).__name__)
            await queue.put({"event": "system_error", "system_id": sid,
                             "message": "This approach could not process the input."})
            return None
        run.inputs[sid] = (source, second)
        run.results[sid] = result
        await queue.put({"event": "result", "system_id": sid, "result": result})
        return result

    for sid, system in configured.items():
        work[sid] = asyncio.create_task(compare(system))
    await asyncio.gather(*work.values())
    # A failure on a primary request can skip awaiting its second transcript. Drain every file reader.
    await asyncio.gather(*set(inputs.values()), return_exceptions=True)


async def run_compare(run_id: str, run: DemoRun, queue: asyncio.Queue, memory: DemoMemory, *,
                      audio: Path | None, upload: tuple[bytes, str] | None, text: str | None,
                      cache_answers: bool) -> None:
    try:
        if upload is None:
            await _dispatch(run, queue, memory, audio=audio, text=text, cache_answers=cache_answers)
        else:
            uploads = path("cache") / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(dir=uploads) as temp:
                content, extension = upload
                file = Path(temp) / f"call{extension}"
                file.write_bytes(content)
                await _dispatch(run, queue, memory, audio=file, text=None, cache_answers=False)
    except Exception as exc:
        _logger.error("Demo run %s failed (%s)", run_id, type(exc).__name__)
        for sid in systems():
            if sid not in run.results:
                await queue.put({"event": "system_error", "system_id": sid, "message": "Comparison could not start."})
    finally:
        await queue.put({"event": "done", "run_id": run_id})


async def replay(run: DemoRun, system: dict, memory: DemoMemory) -> dict:
    start = time.perf_counter()
    source, second = run.inputs[system["id"]]
    result = await _worker(run_system, system, run, source, second, memory, replay=True)
    return {**result, "replay_ms": round((time.perf_counter() - start) * 1000, 2)}
