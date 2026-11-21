"""
Who may spend OpenAI credits, and who may touch private endpoints.

The app is locked unless it is told otherwise. `make serve` sets PEHCHAAN_MODE=local on the builder's laptop.
Anywhere else (a public URL) recording and test-script endpoints do not exist, sample calls replay from packaged answers
at no cost, and live audio needs the demo passcode and fits inside a per-minute and per-day budget.
"""
from __future__ import annotations

import hmac
import os
import sqlite3
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Annotated

from fastapi import Header, HTTPException, Request

from pehchaan.config import ROOT, settings

_windows: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def is_public() -> bool:
    return os.environ.get("PEHCHAAN_MODE", "public") != "local"


def passcode() -> str:
    return os.environ.get("PEHCHAAN_DEMO_PASSCODE", "")


def local_only() -> None:
    if is_public():
        raise HTTPException(404, "Not found")


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"     # never trust a client-supplied forwarding header


def rate_limit(request: Request, bucket: str, per_minute: int) -> None:
    now = time.monotonic()
    with _lock:
        window = _windows[f"{bucket}:{_client(request)}"]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= per_minute:
            raise HTTPException(429, "Too many requests. Try again in a minute.")
        window.append(now)


def _spend_daily_budget(limit: int) -> None:
    file = ROOT / settings()["demo"]["access_db"]
    file.parent.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d")
    db = sqlite3.connect(file)
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS live_runs (day TEXT PRIMARY KEY, n INTEGER NOT NULL)")
            db.execute("INSERT INTO live_runs VALUES (?, 0) ON CONFLICT (day) DO NOTHING", (today,))
            spent = db.execute("UPDATE live_runs SET n = n + 1 WHERE day = ? AND n < ?", (today, limit)).rowcount
    finally:
        db.close()
    if not spent:
        raise HTTPException(429, "Today's live demo budget is used up. The sample calls still work.")


def check_live(request: Request, supplied: str | None) -> None:
    """Call before any request that can reach a paid model."""
    if not is_public():
        return
    cfg = settings()["demo"]
    expected = passcode()
    if not expected:
        raise HTTPException(403, "Live audio is turned off on this deployment. The sample calls still work.")
    rate_limit(request, "passcode", cfg["public_passcode_tries_per_minute"])
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(401, "Enter the demo passcode to use live audio.")
    rate_limit(request, "live", cfg["public_live_runs_per_minute"])
    _spend_daily_budget(cfg["public_live_runs_per_day"])


def require_live(request: Request, x_demo_passcode: Annotated[str | None, Header()] = None) -> None:
    check_live(request, x_demo_passcode)
