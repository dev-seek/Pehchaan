"""
How different two fingerprints SOUND: 0 = same, 1 = unrelated.

Weighted edit distance: swapping sounds that are easy to mishear (t/d, p/b, v/b, r/l, n/m, vowel/vowel)
costs less than swapping unrelated sounds. A hand-built, explainable cousin of articulatory-feature distances
(cf. PanPhon), tuned for Indian speech. All costs come from settings.yaml `sound:`.
"""
from __future__ import annotations

from functools import lru_cache

from ..config import settings
from .fingerprint import VOWELS, word_keys


@lru_cache(maxsize=1)
def _costs() -> dict:
    s = settings()["sound"]
    return {**s, "similar": {pair: float(c) for pair, c in s["similar_pairs"].items()}}


def _substitution_cost(a: str, b: str) -> float:
    if a == b:
        return 0.0
    c = _costs()
    if a in VOWELS and b in VOWELS:
        return c["vowel_substitution"]
    return c["similar"].get(a + b, c["similar"].get(b + a, c["unrelated_substitution"]))


def _insert_delete_cost(ch: str) -> float:
    c = _costs()
    if ch in VOWELS:
        return c["vowel_insert_delete"]
    if ch == "h":
        return c["h_insert_delete"]
    return c["consonant_insert_delete"]


@lru_cache(maxsize=300_000)
def key_distance(a: str, b: str) -> float:
    """Normalised weighted edit distance between two fingerprints."""
    if a == b:
        return 0.0
    if not a or not b:
        return 1.0
    prev = [0.0]
    for ch in b:
        prev.append(prev[-1] + _insert_delete_cost(ch))
    for ca in a:
        cur = [prev[0] + _insert_delete_cost(ca)]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + _insert_delete_cost(ca),
                           cur[j - 1] + _insert_delete_cost(cb),
                           prev[j - 1] + _substitution_cost(ca, cb)))
        prev = cur
    return min(1.0, prev[-1] / max(len(a), len(b)))


def word_aligned_distance(heard: tuple[str, ...], candidate: tuple[str, ...]) -> float:
    """
    Word-by-word distance for spans with the same number of words. A heard word that is a clear prefix of the
    candidate word (Venkat -> Venkateswara) counts as a cheap match: Indians shorten names constantly.
    """
    if len(heard) != len(candidate) or not candidate:
        return 1.0
    c = _costs()
    total, weight = 0.0, 0
    for h, w in zip(heard, candidate, strict=True):
        d = key_distance(h, w)
        if len(h) >= c["prefix_min_len"] and w.startswith(h):
            d = min(d, c["prefix_cost"])
        total += d * len(w)
        weight += len(w)
    return total / max(weight, 1)


def phrase_distance(heard_keys: tuple[str, ...], candidate_keys: tuple[str, ...]) -> float:
    """
    Same word count: compare word by word, so sounds cannot smear across a word boundary ("Narayanguda wale" is not
    "Neha Agarwal"). Different word count: compare the joined sound, so split words still match ("Konda poor").
    """
    if len(heard_keys) == len(candidate_keys) and len(heard_keys) > 1:
        return word_aligned_distance(heard_keys, candidate_keys)
    whole = key_distance("".join(heard_keys), "".join(candidate_keys))
    return min(whole, word_aligned_distance(heard_keys, candidate_keys))


def _is_consonant(ch: str) -> bool:
    return ch not in VOWELS and ch != "h"


def _consonant_edits(a: str, b: str) -> tuple[int, int]:
    """Along the cheapest alignment: (consonants swapped for an unrelated one, consonants added or lost)."""
    unrelated = _costs()["unrelated_substitution"]
    prev = [(0.0, 0, 0)]
    for ch in b:
        cost, swaps, gaps = prev[-1]
        prev.append((cost + _insert_delete_cost(ch), swaps, gaps + _is_consonant(ch)))
    for ca in a:
        cur = [(prev[0][0] + _insert_delete_cost(ca), prev[0][1], prev[0][2] + _is_consonant(ca))]
        for j, cb in enumerate(b, start=1):
            step = _substitution_cost(ca, cb)
            hard = _is_consonant(ca) and _is_consonant(cb) and ca != cb and step >= unrelated
            cur.append(min((prev[j - 1][0] + step, prev[j - 1][1] + hard, prev[j - 1][2]),
                           (prev[j][0] + _insert_delete_cost(ca), prev[j][1], prev[j][2] + _is_consonant(ca)),
                           (cur[j - 1][0] + _insert_delete_cost(cb), cur[j - 1][1], cur[j - 1][2] + _is_consonant(cb))))
        prev = cur
    return prev[-1][1], prev[-1][2]


def consonant_changes(a: str, b: str) -> tuple[int, int]:
    """How two names differ in consonants, word by word. A shortened form of the same word counts as no change."""
    ka, kb = word_keys(a), word_keys(b)
    pairs = zip(ka, kb, strict=True) if len(ka) == len(kb) else [("".join(ka), "".join(kb))]
    swaps = gaps = 0
    for x, y in pairs:
        short, long = sorted((x, y), key=len)
        if len(short) >= _costs()["prefix_min_len"] and long.startswith(short):
            continue
        s, g = _consonant_edits(x, y)
        swaps, gaps = swaps + s, gaps + g
    return swaps, gaps


def distance(a: str, b: str) -> float:
    """Symmetric sound distance between two raw strings in any script (either may be the shortened form)."""
    ka, kb = word_keys(a), word_keys(b)
    return min(phrase_distance(ka, kb), phrase_distance(kb, ka))
