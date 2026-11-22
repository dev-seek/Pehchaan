"""
Verified learning: a confirmed correction is a candidate, and it must earn its place.

  propose -> check it is safe -> replay it on labelled calls -> adopt it, or reject it with the reason -> roll back any time

A user can tap the wrong option, and one bad memory would rewrite every later call. So a correction only becomes
automatic if it sounds like what was heard, is not an everyday word, repairs this call, and harms nothing in a labelled
corpus. Every decision is written to an append-only ledger. The corpus is dev data only: the locked exam never enters.
"""
from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from pehchaan import CallContext, build_pipeline
from pehchaan.config import ROOT, settings
from pehchaan.languages import get_registry
from pehchaan.resolvers.memory import MemoryStore
from pehchaan.sound import key, phrase_distance, word_keys
from pehchaan.text import tokenize
from pehchaan_sdk.finish import run_engine

from .oracle import audit_edits, fact_correct
from .systems import known_names

TRIAL_USER = "learning-trial"
NUMBER_TYPES = frozenset({"PHONE", "PIN", "AMOUNT"})


@dataclass(frozen=True)
class Candidate:
    heard: str
    canonical: str
    etype: str

    def entry(self) -> dict:
        return {"heard_key": key(self.heard), "heard": self.heard, "canonical": self.canonical, "etype": self.etype,
                "count": 1}


class TrialMemory:
    """The memory a candidate would create, held in RAM so a trial can never touch real user data."""

    def __init__(self, entries: Sequence[dict]):
        self.entries = list(entries)

    def load(self, user_id: str) -> list[dict]:
        return self.entries


def load_corpus() -> list[dict]:
    file = ROOT / settings()["learning"]["corpus"]
    if not file.is_file():
        return []
    return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]


def replay(clip: dict, entries: Sequence[dict]):
    ctx = CallContext.build(clip["context"], clip.get("level", "C3"))
    ctx.user_id = TRIAL_USER
    pipeline = build_pipeline(memory=TrialMemory(entries))
    return run_engine(pipeline, clip["text"], ctx, None, clip.get("second_opinion")), ctx


def _check(name: str, passed: bool | None, detail: str) -> dict:
    return {"name": name, "passed": passed, "detail": detail}


def _safety_checks(c: Candidate, adopted: Sequence[dict]) -> list[dict]:
    cfg = settings()["learning"]
    registry = get_registry()
    if c.etype not in cfg["learnable_types"]:
        kind = "numbers are read-only" if c.etype in NUMBER_TYPES else "this type cannot be learned"
        return [_check("learnable_type", False, f"{c.etype}: {kind}")]
    tokens = tokenize(c.heard)
    common = bool(tokens) and all(registry.is_common(t.norm) for t in tokens)
    distance = phrase_distance(word_keys(c.heard), word_keys(c.canonical)) if key(c.heard) and key(c.canonical) else 1.0
    clash = next((a["canonical"] for a in adopted if a["heard_key"] == key(c.heard) and a["etype"] == c.etype
                  and a["canonical"] != c.canonical), None)
    return [
        _check("learnable_type", True, f"{c.etype} may be learned"),
        _check("not_everyday_word", not common,
               f"'{c.heard}' is an everyday word" if common else "not an everyday word"),
        _check("sounds_alike", distance <= cfg["max_sound_distance"],
               f"sound distance {distance:.2f} (limit {cfg['max_sound_distance']})"),
        _check("no_conflict", clash is None,
               f"already learned as '{clash}': undo that first" if clash else "no conflicting memory"),
    ]


def _numbers(result) -> list[tuple[str, str]]:
    return sorted((e.etype.value, e.value) for e in result.entities if e.etype.value in NUMBER_TYPES)


def _call_check(c: Candidate, call: dict, adopted: Sequence[dict]) -> dict:
    before, _ = replay(call, adopted)
    after, _ = replay(call, [*adopted, c.entry()])
    if any(r["rule"] == "known_name_heard" and r["proposed"] == c.canonical for r in after.refused):
        return _check("repairs_this_call", False, f"'{c.heard}' is a real name and the caller did say it")
    if c.canonical not in after.text_out:
        return _check("repairs_this_call", False, "the correction did not apply to this call")
    if _numbers(before) != _numbers(after):
        return _check("repairs_this_call", False, "the correction would change a number")
    return _check("repairs_this_call", True, "this call now states the confirmed value; numbers untouched")


def _corpus_check(c: Candidate, adopted: Sequence[dict], corpus: Sequence[dict]) -> tuple[dict, dict]:
    changed = helped = harmed = damaged = 0
    for clip in corpus:
        base, ctx = replay(clip, adopted)
        trial, _ = replay(clip, [*adopted, c.entry()])
        if base.text_out == trial.text_out:
            continue
        changed += 1
        for fact in clip["entities"]:
            was, now = fact_correct(fact, base.text_out), fact_correct(fact, trial.text_out)
            helped += int(now and not was)
            harmed += int(was and not now)
        edits = audit_edits(base.text_out, trial.text_out, clip["entities"], known_names(ctx))
        damaged += sum(e["kind"] == "damage" for e in edits)
    stats = {"clips_replayed": len(corpus), "clips_changed": changed, "facts_helped": helped, "facts_harmed": harmed,
             "new_damage": damaged}
    ok = harmed == 0 and damaged == 0
    detail = f"{len(corpus)} labelled calls replayed, {changed} changed, {harmed} facts harmed, {damaged} damaged edits"
    return _check("no_regression", ok, detail), stats


def evaluate(c: Candidate, adopted: Sequence[dict], corpus: Sequence[dict], call: dict | None = None) -> dict:
    """Run every check. Expensive replays only run once the cheap safety checks pass."""
    started = time.perf_counter()
    checks = _safety_checks(c, adopted)
    stats = {"clips_replayed": 0, "clips_changed": 0, "facts_helped": 0, "facts_harmed": 0, "new_damage": 0}
    if all(x["passed"] for x in checks):
        if call is not None:
            checks.append(_call_check(c, call, adopted))
        if all(x["passed"] for x in checks):
            if not corpus:
                checks.append(_check("no_regression", False, "no labelled corpus is available"))
            else:
                result, stats = _corpus_check(c, adopted, corpus)
                checks.append(result)
    return {"adopted": all(x["passed"] for x in checks), "checks": checks, **stats,
            "ms": round((time.perf_counter() - started) * 1000, 1)}


class LearningLoop:
    """Owns the path into memory: nothing becomes automatic without passing `evaluate`."""

    def __init__(self, store: MemoryStore, ledger: Path, corpus: Sequence[dict] | None = None):
        self.store, self.path = store, Path(ledger)
        self._corpus = corpus
        self._lock = Lock()

    @property
    def corpus(self) -> Sequence[dict]:
        if self._corpus is None:
            self._corpus = load_corpus()
        return self._corpus

    @contextmanager
    def _db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS learning_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT NOT NULL, at TEXT NOT NULL, decision TEXT NOT NULL
                    CHECK (decision IN ('adopted', 'rejected', 'rolled_back')), heard TEXT NOT NULL, heard_key TEXT NOT NULL,
                    canonical TEXT NOT NULL, etype TEXT NOT NULL, verdict TEXT NOT NULL, undoes INTEGER)""")
                yield db
        finally:
            db.close()

    def _log(self, db, user: str, decision: str, c: dict, verdict: dict, undoes: int | None = None) -> int:
        row = db.execute("""INSERT INTO learning_events (user, at, decision, heard, heard_key, canonical, etype, verdict, undoes)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                         (user, time.strftime("%Y-%m-%d %H:%M:%S"), decision, c["heard"], c["heard_key"], c["canonical"],
                          c["etype"], json.dumps(verdict, ensure_ascii=False), undoes))
        return row.lastrowid

    def propose(self, user: str, heard: str, canonical: str, etype: str, call: dict | None = None) -> dict:
        candidate = Candidate(heard, canonical, etype)
        with self._lock:
            verdict = evaluate(candidate, self.store.load(user), self.corpus, call)
            if verdict["adopted"]:
                self.store.remember(user, heard, canonical, etype)
            with self._db() as db:
                event = self._log(db, user, "adopted" if verdict["adopted"] else "rejected", candidate.entry(), verdict)
        return {"event_id": event, "heard": heard, "canonical": canonical, "etype": etype, **verdict}

    def rollback(self, user: str, event_id: int) -> dict:
        with self._lock, self._db() as db:
            row = db.execute("SELECT * FROM learning_events WHERE id=? AND user=? AND decision='adopted'",
                             (event_id, user)).fetchone()
            if row is None:
                raise KeyError("no adopted correction with this id")
            if db.execute("SELECT 1 FROM learning_events WHERE undoes=?", (event_id,)).fetchone():
                raise KeyError("this correction was already rolled back")
            self.store.remove(user, row["heard_key"], row["etype"])
            event = self._log(db, user, "rolled_back", dict(row), {"reason": "undone by the user"}, undoes=event_id)
        return {"event_id": event, "undoes": event_id, "heard": row["heard"], "canonical": row["canonical"]}

    def history(self, user: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute("SELECT * FROM learning_events WHERE user=? ORDER BY id DESC", (user,)).fetchall()
            undone = {r["undoes"] for r in rows if r["undoes"]}
        return [{"event_id": r["id"], "at": r["at"], "decision": r["decision"], "heard": r["heard"],
                 "canonical": r["canonical"], "etype": r["etype"], "undoes": r["undoes"],
                 "active": r["decision"] == "adopted" and r["id"] not in undone, **json.loads(r["verdict"])} for r in rows]
