"""
SecondOpinion: a transcript of the same audio made WITHOUT any context.

Keyword biasing helps the speech model spell known names, but it also means "the transcript matches the context" is
no longer independent evidence: the model may simply have echoed its keyword. A context-free transcript breaks that
circle, and it works with any speech model because it needs no confidence scores.
"""
from __future__ import annotations

from ..config import settings
from ..languages import LanguageRegistry
from ..models import Entity, EType
from ..numbers import find_runs, rules
from ..sound import phrase_distance, word_keys
from ..text import tokenize


class SecondOpinion:
    def __init__(self, text: str, registry: LanguageRegistry):
        tokens = tokenize(text)
        runs = find_runs(tokens, registry)
        self.word_keys = [word_keys(t.norm) for t in tokens]
        self.digits = {rules.strip_phone_prefix(r.digit_reading) for r in runs if r.digit_reading}
        self.values = {r.value_reading for r in runs if r.value_reading is not None}
        self.max_distance = settings()["policy"]["second_opinion_max_dist"]

    def heard_name(self, name: str) -> bool:
        """Did the context-free transcript hear something that sounds like `name`?"""
        target = word_keys(name)
        if not target:
            return True
        for width in {max(1, len(target) - 1), len(target), len(target) + 1}:
            for start in range(max(0, len(self.word_keys) - width + 1)):
                heard = tuple(k for words in self.word_keys[start:start + width] for k in words)
                if heard and phrase_distance(heard, target) <= self.max_distance:
                    return True
        return False

    def heard_number(self, e: Entity) -> bool:
        if not e.heard_value:
            return False
        if e.etype == EType.AMOUNT:
            return float(e.heard_value) in self.values or e.heard_value in self.digits
        return e.heard_value in self.digits

    def nearest_number(self, e: Entity) -> str | None:
        """The closest number the other transcript heard, offered as an option in the question."""
        pool = {rules.plain_amount(v) for v in self.values} if e.etype == EType.AMOUNT else self.digits
        same_length = [d for d in pool if len(d) == len(e.heard_value)]
        if not same_length:
            return None
        return min(same_length, key=lambda d: (rules.digit_edit_distance(d, e.heard_value), d))
