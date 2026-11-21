"""
Sound fingerprint ("pronunciation key") of a word or phrase.

Spelling differences that do not change how an Indian speaker says a word are erased:
aspiration (th/t, bh/b), vowel length (aa/a, ee/i), sh/s, w/v, z/j, doubled letters, silent final h,
final schwa (Rama/Ram), Telugu final -u (Kondapuru/Kondapur).
"Kondapoor", "Kondaapur", "कोंडापुर" and "కొండాపూర్" all become "kondapur".
"""
from __future__ import annotations

import re
from functools import lru_cache

from ..text import normalize

VOWELS = frozenset("aeiou")

# Ordered rewrite rules (longest first). Language knowledge, not tuning: see settings.yaml `sound` for costs.
_REWRITES: list[tuple[str, str]] = [
    ("sh", "s"), ("kh", "k"), ("gh", "g"), ("jh", "j"), ("th", "t"), ("dh", "d"), ("ph", "f"), ("bh", "b"),
    ("ck", "k"), ("q", "k"), ("x", "ks"), ("z", "j"), ("w", "v"),
    ("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"),
    ("ai", "e"), ("ay", "e"), ("ei", "e"), ("ey", "e"), ("au", "o"), ("ow", "o"), ("ou", "u"),
]


def _word_key(word: str) -> str:
    t = re.sub(r"[^a-z]", "", word)               # letters only; digits belong to the numbers module
    if not t:
        return ""
    t = re.sub(r"ow$", "ao", t)                   # Row ~ Rao
    t = t.replace("chh", "\x01").replace("ch", "\x01")
    t = re.sub(r"c(?=[eiy])", "s", t)             # English soft c
    t = t.replace("c", "k").replace("\x01", "c")  # 'c' in a key always means the च sound
    for a, b in _REWRITES:
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)               # doubled letters
    t = re.sub(r"(?<=[^aeiou])y$", "i", t)        # final y after consonant: reddy -> redi
    t = re.sub(r"h$", "", t)                      # silent final h
    if len(t) > 3 and t[-1] in "au" and t[-2] not in VOWELS:
        t = t[:-1]                                # final schwa / Telugu final -u
    return t


@lru_cache(maxsize=100_000)
def word_keys(text: str) -> tuple[str, ...]:
    """Fingerprint of each word in `text` (any script)."""
    return tuple(k for k in (_word_key(w) for w in normalize(text).split()) if k)


@lru_cache(maxsize=100_000)
def key(text: str) -> str:
    """Fingerprint of a whole phrase (word keys joined)."""
    return "".join(word_keys(text))
