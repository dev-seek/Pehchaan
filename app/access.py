"""
Who may spend OpenAI credits, and who may touch private endpoints.

The app is locked unless it is told otherwise. `make serve` sets PEHCHAAN_MODE=local on the builder's laptop, and
ENV=production always wins over it. Anywhere else (a public URL) recording and test-script endpoints do not exist, sample
calls replay from packaged answers at no cost, and live inference needs the demo passcode or the caller's own OpenAI key.
A caller's key is used for that one request. It is never stored, logged or replaced by the server's key.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Annotated

from fastapi import Header, HTTPException, Request
from starlette.requests import HTTPConnection

from pehchaan.config import ROOT, settings

_windows: dict[str, deque] = defaultdict(deque)
_lock = Lock()


@dataclass(frozen=True)
class Credential:
    kind: str  # local | passcode | byok | free (pasted text only: no paid model can run)
    openai_key: str | None = field(default=None, repr=False)

    @property
    def tenant(self) -> str:
        """Whose memory this is. A hash, so the key itself is never used as a name."""
        if self.kind != "byok":
            return self.kind
        return "byok-" + hashlib.sha256((self.openai_key or "").encode()).hexdigest()[:16]


def is_public() -> bool:
    return os.environ.get("ENV") == "production" or os.environ.get("PEHCHAAN_MODE", "public") != "local"


def passcode() -> str:
    return os.environ.get("PEHCHAAN_DEMO_PASSCODE") or os.environ.get("DEMO_PASSCODE", "")


def local_only() -> None:
    if is_public():
        raise HTTPException(404, "Not found")


def _client(conn: HTTPConnection) -> str:
    return conn.client.host if conn.client else "unknown"  # set by uvicorn, which trusts only the local proxy


def rate_limit(
    conn: HTTPConnection,
    bucket: str,
    limit: int,
    window_s: int = 60,
    message: str = "Too many requests. Try again in a minute.",
) -> None:
    now = time.monotonic()
    with _lock:
        window = _windows[f"{bucket}:{_client(conn)}"]
        while window and now - window[0] > window_s:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(429, message)
        window.append(now)


def remaining(conn: HTTPConnection, bucket: str, limit: int, window_s: int) -> int:
    """How many requests this address has left in the window, without using one."""
    now = time.monotonic()
    with _lock:
        used = sum(now - stamp <= window_s for stamp in _windows.get(f"{bucket}:{_client(conn)}", ()))
    return max(0, limit - used)


def _spend_daily_budget(limit: int, kind: str = "") -> None:
    file = ROOT / settings()["demo"]["access_db"]
    file.parent.mkdir(parents=True, exist_ok=True)
    today = time.strftime("%Y-%m-%d") + (f":{kind}" if kind else "")  # a caller's own key cannot use up the demo budget
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


def spend(conn: HTTPConnection, credential: Credential) -> None:
    """
    Live calls are not counted by default (D-049): the passcode is what protects the server's OpenAI credit.
    An operator can set a cap for passcode calls in config. A customer's own key is their own money and is never capped.
    """
    if credential.kind != "passcode":
        return
    hourly, daily = settings()["api"]["per_ip_per_hour"], settings()["demo"]["public_live_runs_per_day"]
    if hourly is not None:
        rate_limit(conn, "live-hour", hourly, 3600, "This address reached its hourly limit. The sample calls still work.")
    if daily is not None:
        _spend_daily_budget(daily)


def _looks_like_key(value: str | None) -> bool:
    return bool(value) and value.startswith("sk-") and len(value) >= 20 and value.isascii() and " " not in value


def authenticate(
    conn: HTTPConnection,
    *,
    demo_passcode: str | None = None,
    openai_key: str | None = None,
    authorization: str | None = None,
) -> Credential:
    """
    Accepts X-Demo-Passcode, X-OpenAI-Key, or `Authorization: Bearer <either>`.
    The bearer form is what the official OpenAI clients send, so they work with only `base_url` changed.
    """
    bearer = authorization[7:].strip() if authorization and authorization.lower().startswith("bearer ") else None
    key = openai_key or (bearer if _looks_like_key(bearer) else None)
    if key and not _looks_like_key(key):
        raise HTTPException(401, "That does not look like an OpenAI API key.")
    if not is_public():
        return Credential("byok", key) if key else Credential("local")
    if key:
        return Credential("byok", key)
    expected, offered = passcode(), demo_passcode or bearer
    if not offered:
        raise HTTPException(401, "Send X-Demo-Passcode, or your own OpenAI key in X-OpenAI-Key.")
    if not expected:
        raise HTTPException(403, "The demo passcode is turned off here. Use your own OpenAI key.")
    if not _passcode_matches(conn, offered, expected):
        raise HTTPException(401, "That passcode is not correct.")
    return Credential("passcode")


def _passcode_matches(conn: HTTPConnection, offered: str, expected: str) -> bool:
    """Only wrong guesses count toward the guessing limit, so a correct passcode can make any number of calls."""
    limit = settings()["demo"]["public_passcode_tries_per_minute"]
    if remaining(conn, "passcode", limit, 60) <= 0:
        raise HTTPException(429, "Too many wrong passcodes. Try again in a minute.")
    if hmac.compare_digest(offered.encode(), expected.encode()):
        return True
    rate_limit(conn, "passcode", limit)
    return False


def inference_or_free(
    request: Request,
    x_demo_passcode: Annotated[str | None, Header()] = None,
    x_openai_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Credential:
    """For routes that need no paid model: a visitor with no credential can still check pasted text."""
    if is_public() and not (x_demo_passcode or x_openai_key or authorization):
        rate_limit(request, "free", settings()["api"]["free_requests_per_minute"])
        return Credential("free")
    return authenticate(request, demo_passcode=x_demo_passcode, openai_key=x_openai_key, authorization=authorization)


def require_inference(
    request: Request,
    x_demo_passcode: Annotated[str | None, Header()] = None,
    x_openai_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Credential:
    return authenticate(request, demo_passcode=x_demo_passcode, openai_key=x_openai_key, authorization=authorization)


def check_live(request: Request, supplied: str | None) -> None:
    """Call before any older demo route that can reach a paid model. These routes take the passcode only."""
    if not is_public():
        return
    cfg = settings()["demo"]
    expected = passcode()
    if not expected:
        raise HTTPException(403, "Live audio is turned off on this deployment. The sample calls still work.")
    if not supplied or not _passcode_matches(request, supplied, expected):
        raise HTTPException(401, "Enter the demo passcode to use live audio.")
    if cfg["public_live_runs_per_minute"] is not None:
        rate_limit(request, "live", cfg["public_live_runs_per_minute"])
    spend(request, Credential("passcode"))


def require_live(request: Request, x_demo_passcode: Annotated[str | None, Header()] = None) -> None:
    check_live(request, x_demo_passcode)
