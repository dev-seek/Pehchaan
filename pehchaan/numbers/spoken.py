"""
Read spoken numbers out of a token list, in any active language (number words come from the language packs).

A "run" is a stretch of number tokens: "98480 12345", "nine eight double four…", "चौदह हज़ार पाँच सौ",
"नाइन एट फोर". Every run gets two readings:
  digit reading - glue each piece's digits together (how phone numbers and PINs are spoken)
  value reading - Indian-system arithmetic with hundred/thousand/lakh/crore, dedh/dhai/saade (how amounts are spoken)
Which reading is right is decided later by resolvers.numbers using cue words and validity rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..config import settings
from ..languages import LanguageRegistry
from ..models import Token

DIGITS = re.compile(r"^\d+$")
CONNECTORS = {"and", "aur"}


@dataclass
class NumberRun:
    start: int                   # token index, inclusive
    end: int                     # token index, exclusive
    words: list[str]             # normalised tokens of the run (connectors removed)
    digit_reading: str
    value_reading: float | None
    has_multiplier: bool
    teen_ty_alternatives: list[float] = field(default_factory=list)


def _kind(w: str, r: LanguageRegistry) -> str | None:
    if DIGITS.match(w):
        return "digits"
    if r.repeater(w) is not None:
        return "repeat"
    if r.multiplier(w) is not None:
        return "multiplier"
    if r.fraction(w) is not None:
        return "fraction"
    if r.shift_modifier(w) is not None:
        return "shift"
    if r.number_value(w) is not None:
        return "word"
    return None


def find_runs(tokens: list[Token], registry: LanguageRegistry) -> list[NumberRun]:
    """Maximal runs of number tokens. Weak words ('do', 'ek', 'too') count only inside a longer run."""
    words = [t.norm for t in tokens]
    kinds = [_kind(w, registry) for w in words]
    runs: list[NumberRun] = []
    i = 0
    while i < len(words):
        if kinds[i] is None:
            i += 1
            continue
        j = i
        while j < len(words) and (kinds[j] is not None or (
                words[j] in CONNECTORS and j > i and j + 1 < len(words) and kinds[j + 1] is not None)):
            j += 1
        j = _end_of_digit_string(words, kinds, i, j)
        seg = [w for w in words[i:j] if w not in CONNECTORS]
        if any(not registry.is_weak_number(w) for w in seg) or len(seg) >= 2:
            run = _read(seg, i, j, registry)
            if run:
                runs.append(run)
        i = j
    return runs


def _end_of_digit_string(words: list[str], kinds: list[str | None], start: int, end: int) -> int:
    """'98480 12345 aur 2 hazaar' is a phone number, then an amount. A long digit group ends before later money words."""
    multiplier = next((k for k in range(start, end) if kinds[k] == "multiplier"), None)
    if multiplier is None:
        return end
    long_group = settings()["numbers"]["long_digit_group"]
    last = next((k for k in range(multiplier - 1, start - 1, -1) if kinds[k] == "digits" and len(words[k]) >= long_group), None)
    return last + 1 if last is not None and multiplier > last + 1 else end


def _read(seg: list[str], start: int, end: int, r: LanguageRegistry) -> NumberRun | None:
    digits = digit_reading(seg, r)
    value = value_reading(seg, r)
    if not digits and value is None:
        return None
    has_mult = any(r.multiplier(w) or r.fraction(w) or r.shift_modifier(w) for w in seg)
    alternatives = []
    for k, w in enumerate(seg):
        swapped = r.teen_ty_swap(w)
        if swapped:
            v = value_reading(seg[:k] + [swapped] + seg[k + 1:], r)
            if v is not None and v != value:
                alternatives.append(v)
    return NumberRun(start, end, seg, digits, value, has_mult, alternatives)


def digit_reading(seg: list[str], r: LanguageRegistry) -> str:
    out: list[str] = []
    repeat = 1
    k = 0
    while k < len(seg):
        w = seg[k]
        if r.repeater(w):
            repeat = r.repeater(w)
            k += 1
            continue
        piece = ""
        if DIGITS.match(w):
            piece = w
        elif r.number_value(w) is not None:
            v = r.number_value(w)
            nxt = r.number_value(seg[k + 1]) if k + 1 < len(seg) else None
            if v >= 20 and v % 10 == 0 and nxt is not None and 0 < nxt < 10:   # "ninety eight" -> 98
                v += nxt
                k += 1
            piece = str(v)
        elif r.multiplier(w):
            piece = "0" * (len(str(r.multiplier(w))) - 1)                     # hundred -> "00"
        out.append(piece * repeat if len(piece) == 1 else piece)
        repeat = 1
        k += 1
    return "".join(out)


def value_reading(seg: list[str], r: LanguageRegistry) -> float | None:
    """'chaudah hazaar paanch sau' -> 14500 · 'saade teen lakh' -> 350000 · 'dedh lakh' -> 150000."""
    if len(seg) == 1 and DIGITS.match(seg[0]):
        return float(seg[0])
    if sum(1 for w in seg if DIGITS.match(w)) > 1 and not any(r.multiplier(w) for w in seg):
        return None                                   # "98480 12345" is a digit string; "2 lakh 40 thousand" is arithmetic
    total = current = shift = 0.0
    seen = False
    for w in seg:
        if r.repeater(w):
            return None
        if DIGITS.match(w) or r.number_value(w) is not None:
            current += (float(w) if DIGITS.match(w) else r.number_value(w)) + shift
            shift, seen = 0.0, True
        elif r.fraction(w) is not None:
            current += r.fraction(w)
            seen = True
        elif r.shift_modifier(w) is not None:
            shift = r.shift_modifier(w)
        elif r.multiplier(w):
            m = r.multiplier(w)
            if m == 100:
                current = (current or 1) * 100
            else:
                total += (current or 1) * m
                current = 0.0
            seen = True
    return total + current if seen else None
