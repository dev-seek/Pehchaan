"""
The single place that talks to OpenAI, plus an on-disk answer cache.

Why a cache: the benchmark re-runs the same clips many times while we tune. Caching every API answer (keyed by a
hash of the exact request) makes re-runs free, fast and reproducible, also for a fresh agent session.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

from .config import ROOT, load_dotenv, settings

_offline: ContextVar[bool] = ContextVar("pehchaan_offline", default=False)
cache_trace: set[Path] | None = None    # tools/pack_demo.py sets this to learn which answers a sample call needs


class OfflineMiss(RuntimeError):
    """A request that must not reach a paid API had no packaged answer."""


@contextmanager
def offline_answers() -> Iterator[None]:
    """Inside this block an uncached request fails instead of spending API credits."""
    token = _offline.set(True)
    try:
        yield
    finally:
        _offline.reset(token)


@lru_cache(maxsize=1)
def client():
    load_dotenv()
    from openai import OpenAI

    return OpenAI()


def _cache_dir(kind: str) -> Path:
    d = ROOT / settings()["paths"]["cache"] / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def request_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def cached(kind: str, payload: dict, call: Callable[[], dict], *, enabled: bool = True) -> tuple[dict, bool]:
    """Return (answer, was_cached). `call()` must return a JSON-serialisable dict; its latency is stored as _ms."""
    f = _cache_dir(kind) / f"{request_hash(payload)}.json" if enabled else None
    if f is not None:
        packaged = ROOT / settings()["demo"]["packaged_answers"] / kind / f.name
        for found in (f, packaged):
            if found.exists():
                if cache_trace is not None:
                    cache_trace.add(found)
                return json.loads(found.read_text(encoding="utf-8")), True
    if _offline.get():
        raise OfflineMiss(f"no packaged {kind} answer")
    t0 = time.time()
    answer = dict(call())
    answer["_ms"] = int((time.time() - t0) * 1000)
    if f is not None:
        with tempfile.NamedTemporaryFile(mode="w", dir=f.parent, encoding="utf-8", delete=False) as tmp:
            try:
                json.dump(answer, tmp, ensure_ascii=False, indent=1)
                tmp.close()
                Path(tmp.name).replace(f)
            finally:
                Path(tmp.name).unlink(missing_ok=True)
    return answer, False


def structured_completion(model: str, system: str, user: str, schema_name: str, schema: dict, timeout: float) -> dict:
    """Chat completion forced to a strict JSON schema (Structured Outputs); returns the parsed object."""
    r = client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
        timeout=timeout,
    )
    return json.loads(r.choices[0].message.content)
