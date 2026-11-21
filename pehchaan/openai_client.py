"""
The single place that talks to OpenAI, plus an on-disk answer cache.

Why a cache: the benchmark re-runs the same clips many times while we tune. Caching every API answer (keyed by a
hash of the exact request) makes re-runs free, fast and reproducible, also for a fresh agent session.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from .config import ROOT, load_dotenv, settings


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


def cached(kind: str, payload: dict, call: Callable[[], dict]) -> tuple[dict, bool]:
    """Return (answer, was_cached). `call()` must return a JSON-serialisable dict; its latency is stored as _ms."""
    f = _cache_dir(kind) / f"{request_hash(payload)}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8")), True
    t0 = time.time()
    answer = dict(call())
    answer["_ms"] = int((time.time() - t0) * 1000)
    f.write_text(json.dumps(answer, ensure_ascii=False, indent=1), encoding="utf-8")
    return answer, False


def structured_completion(model: str, system: str, user: str, schema_name: str, schema: dict,
                          timeout: float) -> dict:
    """Chat completion forced to a strict JSON schema (Structured Outputs); returns the parsed object."""
    r = client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": schema_name, "strict": True, "schema": schema}},
        timeout=timeout,
    )
    return json.loads(r.choices[0].message.content)
