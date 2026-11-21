"""
A LanguagePack is everything language-specific, loaded from data/languages/<code>.yaml:
number words, multipliers, cue words, everyday words, glue words, spelled-letter names, clarifying questions.

The engine never hardcodes a language. Adding one = writing a YAML file and listing its code in settings.
The loader fails fast with a precise message if a file is malformed.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

import yaml

from ..text import normalize

ENTITY_KINDS_WITH_QUESTIONS = ("PERSON", "ORG", "PLACE", "PHONE", "PIN", "AMOUNT")
CUE_KINDS = ("PHONE", "PIN", "AMOUNT", "CURRENCY")


class PackError(ValueError):
    """A language pack file is malformed."""


@dataclass(frozen=True)
class LanguagePack:
    code: str
    name: str
    scripts: tuple[str, ...]
    number_words: Mapping[str, int]
    multipliers: Mapping[str, int]
    fractions: Mapping[str, float]
    shift_modifiers: Mapping[str, float]
    repeaters: Mapping[str, int]
    weak_words: frozenset[str]
    teen_ty_pairs: tuple[tuple[str, str], ...]
    cues: Mapping[str, frozenset[str]]
    everyday_words: frozenset[str]
    glue_words: frozenset[str]
    letter_names: Mapping[str, str]          # normalised spoken form -> letter
    clarify: Mapping[str, Mapping[str, str]]  # etype -> {two|one|none: template}
    canonical: Mapping[str, Mapping[float, str]]  # section -> value -> first listed form (used to generate speech)


def _norm_word(word, where: str) -> str:
    n = normalize(str(word))
    if not n or " " in n:
        raise PackError(f"{where}: '{word}' must normalise to exactly one word (got '{n}')")
    return n


def _value_map(raw: Mapping | None, where: str, cast) -> dict[str, float]:
    out: dict[str, float] = {}
    for value, words in (raw or {}).items():
        if not isinstance(words, list):
            raise PackError(f"{where}.{value}: expected a list of words")
        for w in words:
            out[_norm_word(w, f"{where}.{value}")] = cast(value)
    return out


def _word_set(raw, where: str) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if not isinstance(raw, list):
        raise PackError(f"{where}: expected a list")
    return frozenset(_norm_word(w, where) for w in raw)


def load_pack(path: Path) -> LanguagePack:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PackError(f"{path}: invalid YAML: {e}") from e
    for k in ("code", "name", "scripts", "numbers", "cues", "everyday_words", "glue_words", "clarify"):
        if k not in raw:
            raise PackError(f"{path}: missing required key '{k}'")
    num = raw["numbers"]
    where = f"{path.name}:numbers"
    missing_q = [k for k in ENTITY_KINDS_WITH_QUESTIONS if k not in raw["clarify"]]
    if missing_q:
        raise PackError(f"{path}: clarify is missing {missing_q}")
    canonical = {section: MappingProxyType({float(v): str(ws[0]) for v, ws in (num.get(section) or {}).items() if ws})
                 for section in ("words", "multipliers", "fractions", "shift_modifiers", "repeaters")}
    return LanguagePack(
        code=raw["code"], name=raw["name"], scripts=tuple(raw["scripts"]),
        number_words=MappingProxyType(_value_map(num.get("words"), f"{where}.words", int)),
        multipliers=MappingProxyType(_value_map(num.get("multipliers"), f"{where}.multipliers", int)),
        fractions=MappingProxyType(_value_map(num.get("fractions"), f"{where}.fractions", float)),
        shift_modifiers=MappingProxyType(_value_map(num.get("shift_modifiers"), f"{where}.shift_modifiers", float)),
        repeaters=MappingProxyType(_value_map(num.get("repeaters"), f"{where}.repeaters", int)),
        weak_words=_word_set(num.get("weak"), f"{where}.weak"),
        teen_ty_pairs=tuple((_norm_word(a, where), _norm_word(b, where)) for a, b in num.get("teen_ty_pairs") or []),
        cues=MappingProxyType({k: _word_set(raw["cues"].get(k), f"{path.name}:cues.{k}") for k in CUE_KINDS}),
        everyday_words=_word_set(raw["everyday_words"], f"{path.name}:everyday_words"),
        glue_words=_word_set(raw["glue_words"], f"{path.name}:glue_words"),
        letter_names=MappingProxyType({_norm_word(f, f"{path.name}:letter_names"): str(letter)
                                       for letter, forms in (raw.get("letter_names") or {}).items()
                                       for f in forms}),
        clarify=MappingProxyType({k: MappingProxyType(dict(v)) for k, v in raw["clarify"].items()}),
        canonical=MappingProxyType(canonical),
    )
