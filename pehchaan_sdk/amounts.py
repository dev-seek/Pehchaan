"""
Exact arithmetic for the money forms the frozen engine adds up wrongly (D-052).

It reads "2.5 lakh" as 2 + 5 lakh and "sawa lakh" as one lakh. This module computes those forms from the caller's words.
A value comes only from this arithmetic, never from a model. If the words do not give exactly one value, they stay
as spoken and the caller is asked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import lru_cache

import yaml

from pehchaan import Result, Status
from pehchaan.config import ROOT, settings
from pehchaan.languages import LanguageRegistry, get_registry
from pehchaan.models import Entity, EType, Utterance
from pehchaan.numbers import rules
from pehchaan.output.clarify import question
from pehchaan.output.rewrite import rewrite_with_spans
from pehchaan.text import normalize
from pehchaan.utterance import build_utterance

_NUMBER = re.compile(r"(?<![\w.,])(\d[\d,]*)(?:\.(\d+))?([^\W\d_]*)(?![\w]|\.\d)")
_CURRENCY_BEFORE = re.compile(r"(?:₹|\brs\.?|\binr\b)\s*$", re.I)
_NEXT_WORD = re.compile(r"\s+([^\W\d_]+)")
_RANGE = re.compile(r"(?<![\w.,])\d{1,3}\s*[-–—]\s*\d{1,3}(?:\.\d+)?\s*([^\W\d_]+)")
_MAX_DIGITS = 15
_PREFIX_REACH = 8  # enough for "INR " or "Rs. " before a number, so a long call stays linear
_CONNECTORS = frozenset({"and", "aur"})
UNREADABLE = "These number words do not give one exact amount, so the caller's words were kept."
EXACT = "computed exactly from the caller's words"


@dataclass(frozen=True)
class _Reading:
    start: int
    end: int
    value: Decimal | None  # None: these words do not give one exact amount
    needs_claim: bool = False  # only counts if the engine already read part of these words as money
    needs_cue: bool = False  # "5k" is money only with a money word nearby: "4K TV" and a "10k run" are not


@dataclass(frozen=True)
class _Forms:
    decimal_words: frozenset[str]
    currency_units: dict[str, int]
    short_units: frozenset[str]
    money_words: frozenset[str]


@lru_cache(maxsize=1)
def _forms() -> _Forms:
    file = ROOT / settings()["sdk"]["number_forms"]
    data = yaml.safe_load(file.read_text(encoding="utf-8"))
    return _Forms(
        frozenset(normalize(w) for w in data["decimal_words"]),
        dict(data["currency_units"]),
        frozenset(data["short_units"]),
        frozenset(normalize(w) for w in data["money_words"]),
    )


def _unit(word: str, registry: LanguageRegistry, after_currency: bool) -> int | None:
    word = word.lower()
    return registry.multiplier(word) or (_forms().currency_units.get(word) if after_currency else None)


def _exact_or_none(value: Decimal) -> Decimal | None:
    return value if value < Decimal(settings()["sdk"]["max_exact_amount"]) else None


def _scaled(number: Decimal, unit: int) -> Decimal | None:
    """Exact, or None. Past 15 significant digits a float, and so the final value, would silently round."""
    return None if len(number.as_tuple().digits) > _MAX_DIGITS else _exact_or_none(number * unit)


def _ranges(text: str, registry: LanguageRegistry) -> list[_Reading]:
    """5-7 lakh is two bounds, not one amount. The engine joins the digits into 57 lakh."""
    return [
        _Reading(m.start(), m.end(), None, needs_claim=True)
        for m in _RANGE.finditer(text)
        if registry.multiplier(m.group(1).lower())
    ]


def _digit_readings(text: str, registry: LanguageRegistry) -> list[_Reading]:
    """2.5 lakh, 12.5k, 5k, 2lakh, ₹2.5L and Rs 149.50."""
    out = []
    for m in _NUMBER.finditer(text):
        whole, fraction, glued = m.group(1).replace(",", ""), m.group(2), m.group(3)
        prefix = _CURRENCY_BEFORE.search(text[max(0, m.start() - _PREFIX_REACH) : m.start()])
        start, end = m.start() - (len(prefix.group()) if prefix else 0), m.end()
        unit, unit_word = None, glued.lower()
        if glued:
            unit = _unit(glued, registry, bool(prefix))
            if unit is None:
                if fraction:  # "2.5L" could be litres: the engine's "2" is wrong, and only the caller can say
                    out.append(_Reading(start, end, None, needs_claim=True))
                continue
        elif (following := _NEXT_WORD.match(text, m.end())) and (
            unit := _unit(following.group(1), registry, bool(prefix))
        ):
            end, unit_word = following.end(), following.group(1).lower()
        if fraction is None and not glued:
            continue
        number = Decimal(f"{whole}.{fraction}") if fraction else Decimal(whole)
        if unit is None and not prefix:  # a bare 999.50 is the whole number when the engine read part of it as money
            out.append(_Reading(start, end, _scaled(number, 1), needs_claim=True))
            continue
        value = _scaled(number, unit or 1)
        short = unit_word in _forms().short_units and not prefix
        out.append(_Reading(start, end, value, needs_claim=value is None, needs_cue=short))
    return out


def _spoken_decimals(utt: Utterance, registry: LanguageRegistry) -> list[_Reading]:
    """one point five lakh, two point seven five crore."""
    out, tokens = [], utt.tokens
    for i, token in enumerate(tokens):
        if token.norm not in _forms().decimal_words or i == 0:
            continue
        whole = registry.number_value(tokens[i - 1].norm)
        j, digits = i + 1, ""
        while j < len(tokens) and (d := registry.number_value(tokens[j].norm)) is not None and 0 <= d < 10:
            digits += str(d)
            j += 1
        unit = registry.multiplier(tokens[j].norm) if j < len(tokens) else None
        if whole is None or not digits or not unit:
            continue
        value = _scaled(Decimal(f"{whole}.{digits}"), unit)
        out.append(_Reading(tokens[i - 1].start, tokens[j].end, value, needs_claim=value is None))
    return out


def _with_shift(words: list[str], registry: LanguageRegistry) -> Decimal | None:
    """sawa lakh = 1.25 lakh, paune lakh = 0.75 lakh, do hazaar sawa sau = 2125. None when the words do not add up."""
    total, current, shift = Decimal(0), Decimal(0), None
    for word in words:
        if word in _CONNECTORS:
            continue
        step = registry.shift_modifier(word)
        multiplier = registry.multiplier(word)
        fraction = registry.fraction(word)
        count = Decimal(word) if word.isdigit() else registry.number_value(word)
        if step is not None:
            if shift is not None:
                return None
            shift = Decimal(str(step))
        elif multiplier:
            if shift is not None:
                if abs(shift) != Decimal("0.25"):
                    return None
                current, shift = current + 1 + shift, None
            if multiplier == 100:
                current = (current or 1) * 100
            else:
                total, current = total + (current or 1) * multiplier, Decimal(0)
        elif fraction is not None:
            current += Decimal(str(fraction))
        elif count is not None:
            current, shift = current + Decimal(count) + (shift or 0), None
        else:
            return None
    return None if shift is not None else total + current


def _shift_before_unit(words: list[str], registry: LanguageRegistry) -> bool:
    return any(
        registry.shift_modifier(a) is not None and registry.multiplier(b)
        for a, b in zip(words, words[1:], strict=False)
    )


def _tokens_in(utt: Utterance, start: int, end: int) -> tuple[int, int] | None:
    inside = [i for i, t in enumerate(utt.tokens) if t.start < end and t.end > start]
    return (inside[0], inside[-1] + 1) if inside else None


def _exact(entity: Entity, value: Decimal, utt: Utterance, known: set[float]) -> Entity:
    number = float(value)
    plain = rules.plain_amount(number)
    seen = number in known
    return replace(
        entity,
        value=plain,
        heard_value=plain,
        display=rules.format_inr(number),
        status=Status.CONFIRMED if seen else Status.KEPT,
        source="context" if seen else "rule",
        reason="matches an amount in this user's SMS" if seen else EXACT,
        candidates=[],
        clarifier=None,
        admission="amount_read",
    )


def _ask(entity: Entity, utt: Utterance, registry: LanguageRegistry) -> Entity:
    return replace(
        entity,
        value=entity.surface,
        heard_value=entity.surface,
        display=entity.surface,
        status=Status.FLAGGED,
        source="rule",
        reason=UNREADABLE,
        candidates=[],
        clarifier=question(registry, utt.language.dominant, "AMOUNT", [], entity.surface),
        admission="amount_unreadable",
    )


def _money_word_near(utt: Utterance, first: int, last: int, registry) -> bool:
    cfg, words = (
        settings()["numbers"],
        registry.cue_words("AMOUNT") | registry.cue_words("CURRENCY") | _forms().money_words,
    )
    before, after = max(0, first - cfg["cue_window_before"]), min(len(utt.tokens), last + cfg["cue_window_after"])
    return any(utt.tokens[i].norm in words for i in range(before, after) if not first <= i < last)


def _ask_over(overlapping: list[Entity], entities: list[Entity], utt: Utterance, registry) -> bool:
    first, last = min(e.start_tok for e in overlapping), max(e.end_tok for e in overlapping)
    whole = replace(overlapping[0], start_tok=first, end_tok=last, surface=utt.span_text(first, last))
    entities[:] = [e for e in entities if e not in overlapping]
    entities.append(_ask(whole, utt, registry))
    return True


def _apply(reading: _Reading, entities: list[Entity], utt: Utterance, registry, known: set[float]) -> bool:
    span = _tokens_in(utt, reading.start, reading.end)
    if span is None:
        return False
    first, last = span
    overlapping = [e for e in entities if e.start_tok < last and e.end_tok > first]
    if any(e.etype != EType.AMOUNT or e.admission == "amount_unreadable" for e in overlapping):
        return False
    if reading.needs_claim and not overlapping:
        return False
    if reading.value is None:
        return _ask_over([*overlapping], entities, utt, registry)
    if reading.needs_cue and not _money_word_near(utt, first, last, registry):
        return _ask_over([*overlapping], entities, utt, registry) if overlapping else False
    surface = utt.span_text(first, last)
    if not overlapping:
        fresh = Entity(EType.AMOUNT, surface, first, last, "", "", Status.KEPT, "rule", EXACT)
        entities.append(_exact(fresh, reading.value, utt, known))
        return True
    if any(e.start_tok < first or e.end_tok > last for e in overlapping):  # more number words than this explains
        return _ask_over([*overlapping], entities, utt, registry)
    entities[:] = [e for e in entities if e not in overlapping]
    entities.append(
        _exact(replace(overlapping[0], start_tok=first, end_tok=last, surface=surface), reading.value, utt, known)
    )
    return True


def read_amounts(result: Result, known_amounts=()) -> bool:
    """Correct what the engine misread, in place. Returns True if an answer changed."""
    registry = get_registry()
    utt = build_utterance(result.text_in, registry, None)
    known = {float(a) for a in known_amounts}
    entities = list(result.entities)
    changed = False
    for reading in [
        *_ranges(utt.text, registry),
        *_digit_readings(utt.text, registry),
        *_spoken_decimals(utt, registry),
    ]:
        changed |= _apply(reading, entities, utt, registry, known)
    for i, entity in enumerate(entities):
        if entity.etype != EType.AMOUNT or entity.admission in ("amount_read", "amount_unreadable"):
            continue
        words = [t.norm for t in utt.tokens[entity.start_tok : entity.end_tok]]
        if _shift_before_unit(words, registry):
            value = _with_shift(words, registry)
            value = _exact_or_none(value) if value is not None else None
            entities[i] = _exact(entity, value, utt, known) if value is not None else _ask(entity, utt, registry)
            changed = True
    if changed:
        entities.sort(key=lambda e: e.start_tok)
        result.entities = entities
        result.text_out, result.spans = rewrite_with_spans(utt, entities, registry)
        result.questions = [
            {"entity": i, "etype": e.etype.value, "question": e.clarifier}
            for i, e in enumerate(entities)
            if e.status == Status.FLAGGED and e.clarifier
        ]
    return changed
