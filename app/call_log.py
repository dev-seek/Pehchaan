"""
Saved calls (D-049): what each named caller said and what Pehchaan decided.

A call is saved only when its context names a caller. Text, facts and timings are kept. Audio and keys never are.
Rows belong to one credential, so a customer can only read or delete its own. A failed save never breaks a call.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from pehchaan.config import ROOT, settings
from pehchaan_sdk import VerifyResult

_logger = logging.getLogger(__name__)


class CallLog:
    def __init__(self, file: Path, max_mb: int):
        self.file, self.max_bytes = Path(file), max_mb * 1024 * 1024

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.file, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, caller TEXT NOT NULL, at REAL NOT NULL,
                    source TEXT NOT NULL, language TEXT, context TEXT NOT NULL, result TEXT NOT NULL)""")
                db.execute("CREATE INDEX IF NOT EXISTS calls_by_caller ON calls (tenant, caller, at)")
                yield db
        finally:
            db.close()

    def save(
        self, tenant: str, caller: str, source: str, language: str | None, context: dict, result: dict
    ) -> str | None:
        """Returns the call id, or None when the log is full. Old calls are never dropped to make room."""
        if self.file.exists() and self.file.stat().st_size >= self.max_bytes or not self.max_bytes:
            _logger.warning("the call log is full, so this call was not saved")
            return None
        call_id = uuid.uuid4().hex
        row = (call_id, tenant, caller, time.time(), source, language, _dump(context), _dump(result))
        with self._db() as db:
            db.execute("INSERT INTO calls VALUES (?, ?, ?, ?, ?, ?, ?, ?)", row)
        return call_id

    def calls(self, tenant: str, caller: str, limit: int) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT * FROM calls WHERE tenant = ? AND caller = ? ORDER BY at DESC LIMIT ?", (tenant, caller, limit)
            ).fetchall()
        return [_public(row) for row in rows]

    def get(self, tenant: str, call_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM calls WHERE tenant = ? AND id = ?", (tenant, call_id)).fetchone()
        return {**_public(row), "context": json.loads(row["context"])} if row else None

    def delete(self, tenant: str, call_id: str) -> bool:
        with self._db() as db:
            return db.execute("DELETE FROM calls WHERE tenant = ? AND id = ?", (tenant, call_id)).rowcount > 0

    def forget(self, tenant: str, caller: str) -> int:
        with self._db() as db:
            return db.execute("DELETE FROM calls WHERE tenant = ? AND caller = ?", (tenant, caller)).rowcount


def _dump(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)


def _public(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "caller": row["caller"],
        "at": row["at"],
        "source": row["source"],
        "language": row["language"],
        "result": json.loads(row["result"]),
    }


def call_log() -> CallLog:
    cfg = settings()["api"]
    return CallLog(ROOT / cfg["calls_db"], cfg["calls_max_mb"])


def named_caller(raw: str | dict | None) -> str | None:
    """The caller id as the customer wrote it. `parse_context` has already checked that the context is valid."""
    if not raw:
        return None
    data = json.loads(raw) if isinstance(raw, str) else raw
    name = data.get("user_id") or (data.get("user") or {}).get("id")
    return str(name).strip()[:80] or None if name else None


def record_call(
    tenant: str, raw_context, context: dict, result: VerifyResult, source: str, language: str | None = None
) -> VerifyResult:
    """Save a finished call when it names a caller. Saving is best effort: the caller still gets their answer."""
    caller = named_caller(raw_context)
    if not caller:
        return result
    try:
        call_id = call_log().save(tenant, caller, source, language, context, result.model_dump(exclude={"call_id"}))
    except (sqlite3.Error, OSError) as exc:
        _logger.warning("could not save a call (%s)", type(exc).__name__)
        return result
    return result.model_copy(update={"call_id": call_id})
