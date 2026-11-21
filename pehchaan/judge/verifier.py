"""
The Judge: a small LLM consulted ONLY for genuinely ambiguous name/place/brand matches.

Interface-first: the pipeline depends on the `Judge` protocol, not on OpenAI. Tests inject a fake judge; production
uses `OpenAIJudge`. The judge must answer from a fixed menu (Structured Outputs): keep | cand1 | cand2 | cand3 | flag.

Its rules (adapted from LLM named-entity revision research): replace only if
 (1) the heard span and the candidate plausibly refer to the same thing,
 (2) the difference is plausibly a mishearing (similar sounds, shortened name, split word),
 (3) the sentence still makes sense. Otherwise keep; if it is clearly important but unclear, flag.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from ..config import settings
from ..openai_client import cached, structured_completion

CHOICES = ("keep", "cand1", "cand2", "cand3", "flag")

SYSTEM_PROMPT = (
    "You check ONE entity in an Indian phone-call transcript produced by speech recognition. "
    "The caller may mix Hindi/Telugu/English. You get the sentence, the exact heard span, and up to three "
    "candidate entities from the phone's own context (contacts, caller ID, SMS, saved places, known brands). "
    "Choose a candidate ONLY if all three hold: (1) the span and candidate plausibly refer to the same thing, "
    "(2) the difference is plausibly a mishearing (similar sounds, shortened name, split word), "
    "(3) the sentence still makes sense. Indians often shorten names (Venkat for Venkateswara) - that counts. "
    "Never choose a candidate just because it is in the list. If none fits, answer keep. "
    "If the span is clearly an important name/place/brand but you cannot tell which candidate, answer flag."
)

SCHEMA = {
    "type": "object",
    "properties": {"choice": {"type": "string", "enum": list(CHOICES)}, "reason": {"type": "string"}},
    "required": ["choice", "reason"],
    "additionalProperties": False,
}


@dataclass
class JudgeDecision:
    choice: str        # one of CHOICES
    reason: str
    latency_ms: int = 0
    cached: bool = False


class Judge(Protocol):
    def decide(self, sentence: str, span: str, etype: str, options: list[dict],
               asr_confidence: float | None) -> JudgeDecision: ...


class OpenAIJudge:
    """Judge backed by an OpenAI chat model (settings.models.verifier), with answer caching."""

    def __init__(self, model: str | None = None, timeout_s: float | None = None, *, cache_answers: bool = True):
        cfg = settings()
        self.model = model or cfg["models"]["verifier"]
        self.timeout_s = timeout_s or cfg["verifier"]["timeout_s"]
        self.cache_answers = cache_answers
        self.requests = 0
        self.cache_hits = 0

    def decide(self, sentence: str, span: str, etype: str, options: list[dict],
               asr_confidence: float | None) -> JudgeDecision:
        user = json.dumps({
            "sentence": sentence, "heard_span": span, "entity_type": etype,
            "asr_confidence_logprob": asr_confidence,
            "candidates": {f"cand{i + 1}": {"text": o["text"], "from": o["source"],
                                             "sound_distance_0_to_1": o["distance"]}
                           for i, o in enumerate(options[:3])},
        }, ensure_ascii=False)
        def call() -> dict:
            self.requests += 1
            return structured_completion(self.model, SYSTEM_PROMPT, user, "entity_decision", SCHEMA, self.timeout_s)

        answer, was_cached = cached("judge", {"model": self.model, "system": SYSTEM_PROMPT, "user": user},
                                    call, enabled=self.cache_answers)
        self.cache_hits += int(was_cached)
        choice = answer.get("choice") if answer.get("choice") in CHOICES else "keep"
        return JudgeDecision(choice, answer.get("reason", ""), answer.get("_ms", 0), was_cached)
