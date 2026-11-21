"""
The Pehchaan pipeline: transcript (+ ASR confidences) + call context -> corrected transcript + fact report.

    utterance  = tokens, confidences, language profile      (pehchaan/utterance.py)
    resolvers  = NumberResolver -> MemoryResolver -> NameResolver   (each claims the spans it decides)
    output     = rewritten transcript + one question per FLAGGED fact

Dependencies are injected (Judge, MemoryStore, registry), so tests use fakes and production uses OpenAI/JSON.
`process()` is the one-line convenience used by the app and the benchmark.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .config import ROOT, settings
from .context import CallContext
from .judge import Judge, OpenAIJudge
from .languages import LanguageRegistry, get_registry
from .models import Entity, Status
from .output import rewrite
from .resolvers import JsonMemoryStore, MemoryResolver, MemoryStore, NameResolver, NumberResolver, Resolver
from .utterance import build_utterance


@dataclass
class Result:
    text_in: str
    text_out: str
    level: str
    language: dict
    entities: list[Entity] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    timings_ms: dict = field(default_factory=dict)

    @property
    def llm_calls(self) -> int:
        return sum(1 for e in self.entities if e.source == "llm")

    def to_dict(self) -> dict:
        return {"text_in": self.text_in, "text_out": self.text_out, "level": self.level, "language": self.language,
                "entities": [e.to_dict() for e in self.entities], "questions": self.questions,
                "timings_ms": self.timings_ms, "llm_calls": self.llm_calls}


class Pipeline:
    def __init__(self, resolvers: list[Resolver], registry: LanguageRegistry):
        self.resolvers = resolvers
        self.registry = registry

    def run(self, text: str, ctx: CallContext, asr_pieces: list[dict] | None = None) -> Result:
        t_start = time.perf_counter()
        utt = build_utterance(text, self.registry, asr_pieces)
        lang = utt.language
        result = Result(text_in=text, text_out=text, level=ctx.level,
                        language={"dominant": lang.dominant, "label": lang.label,
                                  "shares": {k: round(v, 2) for k, v in lang.shares.items()}})
        result.timings_ms["prepare"] = _ms(t_start)
        claimed: set[int] = set()
        for resolver in self.resolvers:
            t0 = time.perf_counter()
            found = resolver.resolve(utt, ctx, claimed)
            result.timings_ms[resolver.name] = _ms(t0)
            for e in found:
                claimed.update(range(e.start_tok, e.end_tok))
            result.entities.extend(found)
        result.entities.sort(key=lambda e: e.start_tok)
        result.text_out = rewrite(utt, result.entities, self.registry)
        result.questions = [{"entity": i, "etype": e.etype.value, "question": e.clarifier}
                            for i, e in enumerate(result.entities) if e.status == Status.FLAGGED and e.clarifier]
        result.timings_ms["total"] = _ms(t_start)
        return result


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)


def default_memory_store() -> MemoryStore:
    return JsonMemoryStore(ROOT / settings()["memory"]["dir"])


def build_pipeline(judge: Judge | None = None, memory: MemoryStore | None = None,
                   registry: LanguageRegistry | None = None) -> Pipeline:
    """Wire the standard resolver order. Pass judge=None to run rules-only (no LLM)."""
    registry = registry or get_registry()
    resolvers: list[Resolver] = [NumberResolver(registry)]
    if settings()["memory"]["enabled"]:
        resolvers.append(MemoryResolver(memory or default_memory_store(), settings()["matching"]["max_window_tokens"]))
    resolvers.append(NameResolver(registry, judge))
    return Pipeline(resolvers, registry)


def process(text: str, ctx: CallContext, asr_pieces: list[dict] | None = None,
            use_judge: bool | None = None, memory: MemoryStore | None = None) -> Result:
    """One-call convenience: default wiring, judge on/off from the argument or settings.verifier.enabled."""
    if use_judge is None:
        use_judge = settings()["verifier"]["enabled"]
    return build_pipeline(judge=OpenAIJudge() if use_judge else None, memory=memory).run(text, ctx, asr_pieces)
