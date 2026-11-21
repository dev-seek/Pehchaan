"""
normalize(): any transcript text -> one comparable lowercase Latin form.
tokenize():  split into Tokens that remember where they came from (so we can rewrite the original text).
"""
from __future__ import annotations

import re

from ..models import Token
from .scripts import dominant_script
from .transliterate import to_latin

_CURRENCY = re.compile(r"(₹|\binr\b|\brs\.?)(?=\s*\d)", re.I)
_DIGIT_SEPARATOR = re.compile(r"(?<=\d)[,\-](?=\d)")
EDGE_PUNCTUATION = ".,!?;:\"'()[]{}<>|।॥…“”‘’"


def normalize(text: str) -> str:
    """Lowercase Latin; '₹14,500' -> 'rs 14500'; punctuation removed; whitespace collapsed."""
    t = to_latin(text)
    t = _CURRENCY.sub(" rs ", t).replace("₹", " rs ")
    t = _DIGIT_SEPARATOR.sub("", t).lower()
    t = re.sub(r"[^\w\s]", " ", t).replace("_", " ")
    return re.sub(r"\s+", " ", t).strip()


def tokenize(text: str) -> list[Token]:
    """Whitespace tokens; edge punctuation excluded from offsets; one raw word may yield several tokens."""
    tokens: list[Token] = []
    for m in re.finditer(r"\S+", text):
        start, end = m.start(), m.end()
        while start < end and text[start] in EDGE_PUNCTUATION:
            start += 1
        while end > start and text[end - 1] in EDGE_PUNCTUATION:
            end -= 1
        if start >= end:
            continue
        core = text[start:end]
        script = dominant_script(core)
        for part in normalize(core).split(" "):
            if part:
                tokens.append(Token(raw=core, norm=part, start=start, end=end, script=script))
    return tokens
