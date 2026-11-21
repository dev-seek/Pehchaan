"""
Turn written values into the words a real caller would SAY (the inverse of the numbers engine).
Used only to build benchmark speech: we control exactly what is spoken, so the label is exact.
Word forms come from the language packs (first listed form = canonical), so there is one source of truth.
"""
from __future__ import annotations

import random

from pehchaan.languages import get_registry
from pehchaan.text import normalize

EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
           "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
SPOKEN_ZERO_HI = "ज़ीरो"   # Hindi speakers say "zero" for the digit 0 in phone numbers, not "shunya"


def _hi(section: str, value: float) -> str:
    return get_registry().packs["hi"].canonical[section][float(value)]


def en_0_99(n: int) -> str:
    if n < 20:
        return EN_ONES[n]
    t, u = divmod(n, 10)
    return EN_TENS[t] + ("" if u == 0 else " " + EN_ONES[u])


def en_amount(n: int) -> str:
    """Indian system in English words: 1450000 -> 'fourteen lakh fifty thousand'."""
    parts = []
    for unit, word in ((10_000_000, "crore"), (100_000, "lakh"), (1000, "thousand")):
        q, n = divmod(n, unit)
        if q:
            parts.append(f"{en_amount(q) if q >= 100 else en_0_99(q)} {word}")
    h, n = divmod(n, 100)
    if h:
        parts.append(f"{EN_ONES[h]} hundred")
    if n:
        parts.append(en_0_99(n))
    return " ".join(parts) or "zero"


def hi_amount(n: int, rng: random.Random, allow_fraction: bool = True) -> str:
    """Hindi (Devanagari) amount, sometimes with डेढ़/ढाई/साढ़े as people actually say it."""
    if allow_fraction and rng.random() < 0.6:
        for unit in (100_000, 1000):
            if n % unit == unit // 2 and n < unit * 10:
                k = n // unit
                word = _hi("multipliers", unit)
                if k == 1:
                    return f"{_hi('fractions', 1.5)} {word}"
                if k == 2:
                    return f"{_hi('fractions', 2.5)} {word}"
                return f"{_hi('shift_modifiers', 0.5)} {_hi('words', k)} {word}"
    parts = []
    for unit in (10_000_000, 100_000, 1000):
        q, n = divmod(n, unit)
        if q:
            parts.append(f"{_hi('words', q) if q < 100 else hi_amount(q, rng, False)} {_hi('multipliers', unit)}")
    h, n = divmod(n, 100)
    if h:
        parts.append(f"{_hi('words', h)} {_hi('multipliers', 100)}")
    if n:
        parts.append(_hi("words", n))
    return " ".join(parts) or _hi("words", 0)


def hinglish_amount(n: int, rng: random.Random) -> str:
    """Hindi amount typed in Latin letters: 'chaudah hazaar paanch sau'."""
    return normalize(hi_amount(n, rng))


def en_digits(d: str, rng: random.Random, group: int | None = 5) -> str:
    """'9848812345' -> 'nine eight four double eight, one two three four five' (double/triple sometimes)."""
    words, i = [], 0
    use_repeaters = rng.random() < 0.6
    while i < len(d):
        j = i
        while j < len(d) and d[j] == d[i]:
            j += 1
        if group and i == group:
            words.append(",")
        crosses_group = bool(group) and i < group < j
        if use_repeaters and j - i in (2, 3) and not crosses_group:
            words.append(f"{'double' if j - i == 2 else 'triple'} {EN_ONES[int(d[i])]}")
            i = j
            continue
        words.append(EN_ONES[int(d[i])])
        i += 1
    return " ".join(words).replace(" ,", ",")


def hi_digits(d: str, group: int | None = 5) -> str:
    out = []
    for i, ch in enumerate(d):
        if group and i == group:
            out[-1] += ","
        out.append(SPOKEN_ZERO_HI if ch == "0" else _hi("words", int(ch)))
    return " ".join(out)
