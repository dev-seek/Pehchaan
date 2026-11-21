"""Execute configured comparison systems against shared speech-to-text inputs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pehchaan import CallContext, build_pipeline
from pehchaan.asr import transcribe
from pehchaan.config import settings
from pehchaan.judge import OpenAIJudge
from pehchaan.resolvers import NullMemoryStore
from pehchaan.resolvers.memory import MemoryStore

from .baselines import naive_fix


def asr_key(system: dict) -> str:
    return system["model_key"] + (f"@{system['keywords_level']}" if system.get("keywords_level") else "")


def primary_key(system: dict, by_id: dict[str, dict]) -> str:
    if system["kind"] == "asr":
        return asr_key(system)
    source = system["input"]
    if source in by_id and by_id[source]["kind"] == "asr":
        return asr_key(by_id[source])
    return source


def needed_transcripts(systems: list[dict]) -> set[str]:
    by_id = {s["id"]: s for s in systems}
    keys = {primary_key(s, by_id) for s in systems}
    return (keys - by_id.keys()) | {s["second_opinion"] for s in systems if s.get("second_opinion")}


def context_at(contexts: dict, level: str) -> CallContext:
    return CallContext.build(contexts["context_adv" if level == "C4" else "context"], level)


@dataclass(frozen=True)
class AsrRequest:
    model: str
    keywords: tuple[str, ...]
    with_logprobs: bool

    def run(self, audio_path: Path, *, cache_answers: bool = True) -> dict:
        cfg = settings()["asr"]
        return transcribe(audio_path, self.model, keywords=list(self.keywords) or None, languages=cfg["languages"],
                          with_logprobs=self.with_logprobs, timeout=cfg["timeout_s"], cache_answers=cache_answers)


def asr_request(contexts: dict, transcript_key: str) -> AsrRequest:
    cfg = settings()
    model_key, _, level = transcript_key.partition("@")
    keywords = context_at(contexts, level).keyword_list(cfg["asr"]["keywords_max"]) if level else []
    return AsrRequest(cfg["models"][model_key], tuple(keywords), model_key == "asr_logprobs")


def ordered_systems(systems: list[dict]) -> list[dict]:
    return sorted(systems, key=lambda s: s["kind"] != "asr")


def known_names(ctx: CallContext) -> list[str]:
    """Everything this system could have pasted in from context, used to detect invented entities."""
    return sorted({c.output for c in ctx.candidates} | {c.text for c in ctx.candidates})


def flag_record(entity) -> dict:
    return {"etype": entity.etype.value, "surface": entity.surface, "value": entity.value,
            "options": [c["text"] for c in entity.candidates]}


def execute_system(system: dict, source: dict, ctx: CallContext, *, second_opinion: dict | None = None,
                   use_judge: bool = True, simulate: bool = False, memory: MemoryStore | None = None,
                   cache_answers: bool = True) -> dict:
    text = source["text"]
    output = {"text": text, "in_text": text, "flags": [], "harness_ms": None, "known": []}
    if system["kind"] == "asr":
        return output
    output["known"] = known_names(ctx)
    if system["kind"] == "naive_llm":
        if simulate:
            return output
        fixed = naive_fix(text, ctx, cache_answers=cache_answers)
        return {**output, "text": fixed["text"], "harness_ms": fixed["ms"], "llm_calls": 1,
                "rewrite_calls": int(not fixed["cached"]), "rewrite_cached": fixed["cached"]}
    if system["kind"] != "pehchaan":
        raise ValueError(f"unknown system kind {system['kind']}")
    judge = OpenAIJudge(cache_answers=cache_answers) if use_judge and not simulate else None
    result = build_pipeline(judge=judge, memory=memory or NullMemoryStore()).run(
        text, ctx, source.get("tokens"), second_opinion["text"] if second_opinion else None)
    return {**output, "text": result.text_out, "harness_ms": result.timings_ms["total"],
            "flags": [flag_record(e) for e in result.entities if e.status.value == "FLAGGED"],
            "llm_calls": result.llm_calls, "entities": [e.to_dict() for e in result.entities],
            "verifier_calls": judge.requests if judge else 0, "verifier_cache_hits": judge.cache_hits if judge else 0,
            "engine": result}
