"""
Find stretches of the transcript that sound like a known entity (contact, brand, locality, saved place).

For every window of 1..N consecutive words we:
  1. skip it if it is only everyday words, contains digits, starts/ends with a glue word ("se", "nundi", "from"),
     or crosses punctuation (names never span commas: "है, अगर" must not become "Neha Agarwal"),
  2. cheaply pre-rank all candidates by fingerprint spelling similarity (rapidfuzz, C-fast),
  3. compute the careful sound distance for the top few,
  4. keep the best non-overlapping windows.
This is the "retrieve phonetically similar entities from a personal database" step of Apple's contextual-ASR
work (top-k candidates; more than ~10 adds noise), adapted to Indian names and scripts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from ..languages import LanguageRegistry
from ..models import Candidate, Utterance
from ..sound import key, phrase_distance, word_keys

PUNCTUATION_BREAKS = set(",.;:!?।॥|()[]")


@dataclass
class Scored:
    candidate: Candidate
    distance: float


@dataclass
class Match:
    start: int
    end: int                      # exclusive token index
    ranked: list[Scored] = field(default_factory=list)

    @property
    def best(self) -> Scored:
        return self.ranked[0]

    @property
    def runner_up(self) -> Scored | None:
        """Closest DIFFERENT entity (aliases of the same brand do not count as competition)."""
        best_output = self.best.candidate.output
        return next((s for s in self.ranked[1:] if s.candidate.output != best_output), None)


class CandidateIndex:
    def __init__(self, candidates: list[Candidate]):
        self.candidates = candidates
        self.keys = [key(c.text) for c in candidates]
        self.word_keys = [word_keys(c.text) for c in candidates]

    def search(self, heard: tuple[str, ...], prefilter_k: int, max_distance: float, min_key_len: int) -> list[Scored]:
        heard_key = "".join(heard)
        if len(heard_key) < 2 or not self.candidates:
            return []
        out = []
        for _, _, i in process.extract(heard_key, self.keys, scorer=fuzz.ratio, limit=prefilter_k):
            cand_words = self.word_keys[i]
            if not self.keys[i] or abs(len(cand_words) - len(heard)) > 1:
                continue
            d = phrase_distance(heard, cand_words)
            if len(self.keys[i]) < min_key_len and d > 0:
                continue                                   # short keys must match exactly
            if d <= max_distance:
                out.append(Scored(self.candidates[i], d))
        out.sort(key=lambda s: (s.distance, not s.candidate.per_call))
        return out


def find_matches(utt: Utterance, index: CandidateIndex, claimed: set[int], registry: LanguageRegistry,
                 cfg: dict) -> list[Match]:
    toks = utt.tokens
    everyday = [registry.is_everyday(t.norm) for t in toks]
    glue = [registry.is_glue(t.norm) for t in toks]
    breaks_after = [i + 1 < len(toks) and any(ch in PUNCTUATION_BREAKS for ch in utt.text[toks[i].end:toks[i + 1].start])
                    for i in range(len(toks))]
    found: list[Match] = []
    for s in range(len(toks)):
        for width in range(1, cfg["max_window_tokens"] + 1):
            e = s + width
            if e > len(toks) or (e - 1) in claimed or toks[e - 1].norm.isdigit():
                break
            if width > 1 and breaks_after[e - 2]:
                break
            if s in claimed or all(everyday[s:e]) or glue[s] or glue[e - 1]:
                continue
            heard = tuple(k for t in toks[s:e] for k in word_keys(t.norm))
            ranked = index.search(heard, cfg["prefilter_top_k"], cfg["consider_max_dist"], cfg["min_key_len"])
            if ranked:
                found.append(Match(s, e, ranked[: cfg["candidates_top_k"] + 2]))
    # lowest distance wins, but a longer span gets a small bonus per extra word: "HDFC बैंक" beats "HDFC" alone
    bonus = cfg["longer_span_bonus"]
    found.sort(key=lambda m: (m.best.distance - bonus * (m.end - m.start - 1), -(m.end - m.start)))
    taken: set[int] = set()
    chosen = []
    for m in found:
        if not any(i in taken for i in range(m.start, m.end)):
            chosen.append(m)
            taken.update(range(m.start, m.end))
    return sorted(chosen, key=lambda m: m.start)
