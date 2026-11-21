"""
KnowledgeHub: ask every connected company system about a call, at the same time, within a strict time budget.

A voice call cannot wait for a slow CRM. A source that is slow, down or broken is skipped and reported, and the call carries on
with what the others returned. A source that keeps failing is rested for a while, so a dead system cannot pile up waiting
threads. An error's message is never kept, because it can quote a URL or a key.
"""

from __future__ import annotations

import queue
import threading
import time
from collections import OrderedDict
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pehchaan.config import settings

from .compiler import Answer, Compiled, compile_knowledge
from .records import CallKey, Knowledge


@runtime_checkable
class KnowledgeSource(Protocol):
    """Anything with a name and `fetch(call)` can feed Pehchaan: a CRM, a bank core, an order system, a database."""

    name: str

    def fetch(self, call: CallKey) -> Knowledge | dict | list | None: ...


def _is_private(source) -> bool:
    return bool(getattr(source, "private", False))


def _records(value) -> list[Knowledge]:
    if value is None:
        return []
    return [Knowledge.of(v) for v in (value if isinstance(value, list | tuple) else [value])]


def _timed_out(error: Exception) -> bool:
    return isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError)


def _ask(source: KnowledgeSource, call: CallKey) -> Answer:
    started = time.perf_counter()
    try:
        records = _records(source.fetch(call))
    except Exception as exc:  # noqa: BLE001 - one broken system must never break a call
        status = "timeout" if _timed_out(exc) else "error"
        ms = round((time.perf_counter() - started) * 1000, 1)
        return Answer(source.name, status, ms, private=_is_private(source))
    status = "ok" if records else "no_record"
    return Answer(source.name, status, round((time.perf_counter() - started) * 1000, 1), records, _is_private(source))


class KnowledgeHub:
    def __init__(self, sources: Sequence[KnowledgeSource], *, timeout_ms: int | None = None):
        cfg = settings()["knowledge"]
        names = [s.name for s in sources]
        if len(set(names)) != len(names):
            raise ValueError("every knowledge source needs its own name")
        if len(sources) > cfg["max_sources"]:
            raise ValueError(f"at most {cfg['max_sources']} knowledge sources can be connected")
        self.sources, self.timeout_ms = list(sources), timeout_ms or cfg["timeout_ms"]
        self._ttl, self._size = cfg["cache_ttl_s"], cfg["cache_entries"]
        self._trip_after, self._rest_s = cfg["breaker_failures"], cfg["breaker_cooldown_s"]
        self._cache: OrderedDict[tuple, tuple[float, list[Answer]]] = OrderedDict()
        self._failures: dict[str, int] = {}
        self._resting_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def _cached(self, key: tuple) -> list[Answer] | None:
        with self._lock:
            hit = self._cache.get(key)
            if hit is None:
                return None
            if time.monotonic() - hit[0] > self._ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return hit[1]

    def _store(self, key: tuple, answers: list[Answer]) -> None:
        if any(a.status in ("timeout", "error", "skipped") for a in answers):
            return  # an incomplete lookup should be tried again on the next phrase
        with self._lock:
            self._cache[key] = (time.monotonic(), answers)
            while len(self._cache) > self._size:
                self._cache.popitem(last=False)

    def _is_resting(self, name: str) -> bool:
        with self._lock:
            return time.monotonic() < self._resting_until.get(name, 0)

    def _note(self, answer: Answer) -> None:
        with self._lock:
            if answer.status in ("timeout", "error"):
                self._failures[answer.name] = self._failures.get(answer.name, 0) + 1
                if self._failures[answer.name] >= self._trip_after:
                    self._resting_until[answer.name] = time.monotonic() + self._rest_s
                    self._failures[answer.name] = 0
            else:
                self._failures.pop(answer.name, None)

    def _fetch(self, call: CallKey) -> list[Answer]:
        """Daemon threads, so a source that hangs forever can neither hold the call nor stop the program exiting."""
        active = [s for s in self.sources if not self._is_resting(s.name)]
        replies: queue.SimpleQueue[Answer] = queue.SimpleQueue()
        for source in active:
            threading.Thread(target=lambda s=source: replies.put(_ask(s, call)), daemon=True).start()
        deadline, got = time.monotonic() + self.timeout_ms / 1000, {}
        while len(got) < len(active):
            try:
                answer = replies.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                break
            got[answer.name] = answer
        answers = []
        for source in self.sources:
            if source in active:
                answer = got.get(source.name) or Answer(
                    source.name, "timeout", self.timeout_ms, private=_is_private(source)
                )
                self._note(answer)
            else:
                answer = Answer(source.name, "skipped", private=_is_private(source))
            answers.append(answer)
        return answers

    def gather(self, raw: dict) -> Compiled:
        """Fetch for this call and compile the answers into `raw`. Never raises because of a source."""
        started = time.perf_counter()
        call = CallKey.from_context(raw)
        if not call.usable:
            answers = [Answer(s.name, "skipped", private=_is_private(s)) for s in self.sources]
        else:
            answers = self._cached(call.cache_key)
            if answers is None:
                answers = self._fetch(call)
                self._store(call.cache_key, answers)
        return compile_knowledge(raw, answers, (time.perf_counter() - started) * 1000)

    def context_for(self, raw: dict) -> dict:
        """A ready context for the REST API or stream. Names from private sources stay on this machine."""
        return {k: v for k, v in self.gather(raw).shareable.items() if k != "customer_id" and v not in (None, [], {})}


def as_hub(knowledge) -> KnowledgeHub | None:
    """Accept a hub, one source, or a list of sources."""
    if knowledge is None or isinstance(knowledge, KnowledgeHub):
        return knowledge
    return KnowledgeHub(list(knowledge) if isinstance(knowledge, list | tuple) else [knowledge])
