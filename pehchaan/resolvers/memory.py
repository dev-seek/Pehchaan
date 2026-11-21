"""
Learned memory: the system gets better with every confirmation.

When a caller or user confirms "it's Kondapur, not Kothapur", we store  sound-fingerprint(heard) -> canonical.
Next time that mishearing appears for this user it is fixed instantly, before any matching or LLM call.

`MemoryStore` is an interface; `JsonMemoryStore` (one small JSON file per user) is enough for the hackathon.
A SQLite/Redis store can replace it without touching the resolver.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Protocol

from ..context import CallContext
from ..models import Entity, EType, Status, Utterance
from ..sound import key

READ_ONLY_TYPES = frozenset({EType.PHONE, EType.PIN, EType.AMOUNT})


class MemoryStore(Protocol):
    def load(self, user_id: str) -> list[dict]: ...
    def remember(self, user_id: str, heard: str, canonical: str, etype: str) -> dict: ...
    def forget(self, user_id: str) -> None: ...


class JsonMemoryStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._lock = Lock()

    def _file(self, user_id: str) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch for ch in user_id if ch.isalnum() or ch in "-_") or "default"
        return self.directory / f"{safe}.json"

    def load(self, user_id: str) -> list[dict]:
        f = self._file(user_id)
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []

    def remember(self, user_id: str, heard: str, canonical: str, etype: str) -> dict:
        if EType(etype) in READ_ONLY_TYPES:            # EType() also fails fast on an unknown type
            raise ValueError(f"{etype} is read-only: a learned correction may never rewrite a number (D-021)")
        entry = {"heard_key": key(heard), "heard": heard, "canonical": canonical, "etype": etype, "count": 1,
                 "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
        with self._lock:
            items = self.load(user_id)
            for it in items:
                if it["heard_key"] == entry["heard_key"] and it["etype"] == etype:
                    it.update(canonical=canonical, updated=entry["updated"], count=it["count"] + 1)
                    entry = it
                    break
            else:
                items.append(entry)
            self._file(user_id).write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
        return entry

    def forget(self, user_id: str) -> None:
        self._file(user_id).unlink(missing_ok=True)


class NullMemoryStore:
    """Remembers nothing. The benchmark uses it so a demo session can never change a measured result."""

    def load(self, user_id: str) -> list[dict]:
        return []

    def remember(self, user_id: str, heard: str, canonical: str, etype: str) -> dict:
        raise RuntimeError("NullMemoryStore cannot store corrections")

    def forget(self, user_id: str) -> None:
        return None


class MemoryResolver:
    name = "memory"

    def __init__(self, store: MemoryStore, max_window_tokens: int):
        self.store = store
        self.max_window = max_window_tokens

    def resolve(self, utt: Utterance, ctx: CallContext, claimed: set[int]) -> list[Entity]:
        if not ctx.user_id:
            return []
        learned = {it["heard_key"]: it for it in self.store.load(ctx.user_id)}
        if not learned:
            return []
        out, taken = [], set(claimed)
        for width in range(self.max_window, 0, -1):          # longest learned phrases first
            for s in range(0, len(utt.tokens) - width + 1):
                e = s + width
                if any(i in taken for i in range(s, e)):
                    continue
                hit = learned.get(key(" ".join(t.norm for t in utt.tokens[s:e])))
                if hit:
                    out.append(Entity(etype=EType(hit["etype"]), surface=utt.span_text(s, e), start_tok=s, end_tok=e,
                                      value=hit["canonical"], display=hit["canonical"], status=Status.FIXED,
                                      source="memory", reason="you confirmed this before: learned correction",
                                      distance=0.0, asr_confidence=utt.min_confidence(s, e)))
                    taken.update(range(s, e))
        return out
