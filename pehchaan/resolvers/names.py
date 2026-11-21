"""
NameResolver: people, organisations, places.

Decision ladder for the best sound-alike candidate of a span (all thresholds in settings.yaml `matching`/`decisions`):
  distance <= verify_max_dist                                  -> CONFIRMED (same sound; canonical spelling written)
  distance <= autofix threshold, clear winner, ASR not certain -> FIXED     (math alone, no LLM)
  close but ambiguous                                          -> ask the Judge (keep / candN / flag), if one is wired in
  no judge, this-call candidate, close enough                  -> FLAGGED   (ask the caller)
  otherwise                                                    -> ignored
Per-call candidates (contacts, caller ID, SMS) are trusted more than big global lists (brands, localities),
because large lists cause false alarms (contextual-biasing research).
"""
from __future__ import annotations

from ..config import settings
from ..context import CallContext
from ..judge import Judge
from ..languages import LanguageRegistry
from ..models import Entity, Status, Utterance
from ..output import question
from .matching import CandidateIndex, Match, find_matches


class NameResolver:
    name = "names"

    def __init__(self, registry: LanguageRegistry, judge: Judge | None):
        self.registry = registry
        self.judge = judge
        cfg = settings()
        self.m, self.d = cfg["matching"], cfg["decisions"]
        self.judge_budget = cfg["verifier"]["max_calls_per_utterance"]

    def resolve(self, utt: Utterance, ctx: CallContext, claimed: set[int]) -> list[Entity]:
        index = CandidateIndex(ctx.candidates)
        budget = self.judge_budget if self.judge else 0
        out = []
        for match in find_matches(utt, index, claimed, self.registry, self.m):
            entity, used_judge = self._decide(match, utt, budget > 0)
            budget -= int(used_judge)
            if entity:
                out.append(entity)
        return out

    def _options(self, match: Match) -> list[dict]:
        opts, seen = [], set()
        for s in match.ranked:
            if s.candidate.output not in seen:
                seen.add(s.candidate.output)
                opts.append({"text": s.candidate.output, "source": s.candidate.source,
                             "distance": round(s.distance, 3), "etype": s.candidate.etype.value})
        return opts[: self.m["candidates_top_k"]]

    def _decide(self, match: Match, utt: Utterance, judge_allowed: bool) -> tuple[Entity | None, bool]:
        best, runner_up = match.best, match.runner_up
        cand = best.candidate
        surface = utt.span_text(match.start, match.end)
        conf = utt.min_confidence(match.start, match.end)
        options = self._options(match)
        base = dict(etype=cand.etype, surface=surface, start_tok=match.start, end_tok=match.end,
                    distance=round(best.distance, 3), asr_confidence=conf, candidates=options)
        source = "context" if cand.per_call else "lexicon"

        if best.distance <= self.m["verify_max_dist"]:
            return Entity(value=cand.output, display=cand.output, status=Status.CONFIRMED, source=source,
                          reason=f"sounds the same as '{cand.output}' from {cand.source}", **base), False

        threshold = self.m["autofix_max_dist"]["per_call" if cand.per_call else "global"]
        if conf is not None and conf < self.m["low_conf_logprob"]:
            threshold += self.m["low_conf_bonus"]
        clear_winner = runner_up is None or runner_up.distance - best.distance >= self.m["min_margin"]
        asr_certain = conf is not None and conf > self.m["high_conf_logprob"]
        if best.distance <= threshold and clear_winner and not asr_certain:
            return Entity(value=cand.output, display=cand.output, status=Status.FIXED, source=source,
                          reason=f"heard '{surface}', sounds like '{cand.output}' from {cand.source} "
                                 f"(distance {best.distance:.2f})", **base), False

        worth_judging = best.distance <= self.d["llm_max_dist"] and (
            cand.per_call or best.distance <= self.m["autofix_max_dist"]["global"] + 0.08)
        lang = utt.language.dominant
        if judge_allowed and worth_judging:
            try:
                verdict = self.judge.decide(utt.text, surface, cand.etype.value, options, conf)
            except Exception as e:  # noqa: BLE001 - an API outage must never break a call
                fallback = f"judge unavailable ({type(e).__name__})"
            else:
                if verdict.choice.startswith("cand") and int(verdict.choice[-1]) <= len(options):
                    chosen = options[int(verdict.choice[-1]) - 1]["text"]
                    return Entity(value=chosen, display=chosen, status=Status.FIXED, source="llm",
                                  reason=f"judge: {verdict.reason}", **base), True
                if verdict.choice == "flag":
                    return Entity(value=surface, display=surface, status=Status.FLAGGED, source="llm",
                                  reason=f"judge: {verdict.reason}",
                                  clarifier=question(self.registry, lang, cand.etype.value,
                                                     [o["text"] for o in options[:2]], surface), **base), True
                return Entity(value=surface, display=surface, status=Status.KEPT, source="llm",
                              reason=f"judge kept it: {verdict.reason}", **base), True
        else:
            fallback = "ambiguous match, judge not used"
        if cand.per_call and cand.etype.value in self.d["flag_types_when_ambiguous"] \
                and best.distance <= self.d["flag_max_dist"]:
            return Entity(value=surface, display=surface, status=Status.FLAGGED, source="rule",
                          reason=f"{fallback}: could be {', '.join(o['text'] for o in options[:2])}",
                          clarifier=question(self.registry, lang, cand.etype.value,
                                             [o["text"] for o in options[:2]], surface), **base), False
        return None, False
