"""Hold short-lived compare inputs and explicitly confirmed names and places."""

from __future__ import annotations

import sqlite3
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from pehchaan.config import settings
from pehchaan.sound import key

MEMORY_TYPES = frozenset(settings()["learning"]["learnable_types"])


class DemoMemory:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        try:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS confirmations (
                    session TEXT NOT NULL, heard_key TEXT NOT NULL, etype TEXT NOT NULL,
                    heard TEXT NOT NULL, canonical TEXT NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY (session, heard_key, etype),
                    CHECK (etype IN ('PERSON', 'ORG', 'PLACE')))""")
                yield db
        finally:
            db.close()

    def load(self, user_id: str) -> list[dict]:
        if not self.path.exists():
            return []
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            return [
                dict(row)
                for row in db.execute(
                    "SELECT heard_key, etype, heard, canonical, count FROM confirmations WHERE session=? ORDER BY rowid",
                    (user_id,),
                )
            ]

    def remember(self, user_id: str, heard: str, canonical: str, etype: str) -> dict:
        heard_key = key(heard)
        if (
            etype not in MEMORY_TYPES
            or not heard_key
            or not key(canonical)
            or any(char.isdecimal() for char in heard + canonical)
            or not canonical.isprintable()
        ):
            raise ValueError("enter a valid name or place")
        with self._connect() as db:
            db.execute(
                """INSERT INTO confirmations VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT (session, heard_key, etype) DO UPDATE
                SET heard=excluded.heard, canonical=excluded.canonical, count=count+1""",
                (user_id, heard_key, etype, heard, canonical),
            )
        return {"heard": heard, "canonical": canonical, "etype": etype}

    def forget(self, user_id: str) -> None:
        if self.path.exists():
            with self._connect() as db:
                db.execute("DELETE FROM confirmations WHERE session=?", (user_id,))

    def remove(self, user_id: str, heard_key: str, etype: str) -> None:
        if self.path.exists():
            with self._connect() as db:
                db.execute("DELETE FROM confirmations WHERE session=? AND heard_key=? AND etype=?",
                           (user_id, heard_key, etype))


@dataclass
class DemoRun:
    session: str
    contexts: dict
    truth: dict | None = None
    created_at: float = field(default_factory=time.monotonic)
    inputs: dict[str, tuple[dict, dict | None]] = field(default_factory=dict)
    results: dict[str, dict] = field(default_factory=dict)


class DemoRuns:
    def __init__(self):
        self._runs: OrderedDict[str, DemoRun] = OrderedDict()
        self._lock = Lock()

    def save(self, run_id: str, run: DemoRun) -> None:
        with self._lock:
            self._prune()
            self._runs[run_id] = run
            while len(self._runs) > settings()["demo"]["max_saved_runs"]:
                self._runs.popitem(last=False)

    def expire(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)

    def find(self, run_id: str, session: str | None) -> DemoRun | None:
        with self._lock:
            self._prune()
            run = self._runs.get(run_id)
            return run if run and session == run.session else None

    def _prune(self):
        cutoff = time.monotonic() - settings()["demo"]["run_ttl_s"]
        for run_id in [rid for rid, run in self._runs.items() if run.created_at < cutoff]:
            del self._runs[run_id]
