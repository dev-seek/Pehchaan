"""Edit audit: align input and output, classify every changed chunk as format / repair / damage."""
from __future__ import annotations

import functools
from collections.abc import Iterable
from difflib import SequenceMatcher

import yaml

from .names import name_present, phon, same_name
from .numbers import YAML_PATH, Unit, fold, light, number_fact, segment


@functools.lru_cache(maxsize=1)
def _currency_words() -> frozenset[str]:
    words = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))["currency_words"]
    return frozenset(fold(w) for w in words.split())


def _only_currency(units: list[Unit]) -> bool:
    return bool(units) and all(not u.is_number and fold(u.surface) in _currency_words() for u in units)


def _fact(entity: dict, text: str) -> bool:
    if entity["type"] in ("PHONE", "PIN", "AMOUNT"):
        return number_fact(entity, text)
    return name_present(str(entity["value"]), text)


def _contains(name_keys: tuple[str, ...], units: list[Unit]) -> bool:
    keys = [u.key for u in units]
    n = len(name_keys)
    return n > 0 and any(tuple(keys[i:i + n]) == name_keys for i in range(len(keys) - n + 1))


def _facts(units: list[Unit]) -> tuple[set, set]:
    nums = [u for u in units if u.is_number]
    return {u.digits for u in nums if u.digits}, {u.value for u in nums if u.value is not None}


def _classify(before: list[Unit], after: list[Unit], ents: list[dict],
              known: list[tuple[str, tuple[str, ...]]]) -> tuple[str, str]:
    bt, at = " ".join(u.surface for u in before), " ".join(u.surface for u in after)
    if _only_currency(before + after):
        return "format", "currency_word"           # "14500 rupaye" -> "₹14,500" states the same amount
    for e in ents:
        if _fact(e, at) and not _fact(e, bt):
            return "repair", f"now states {e['type']} {e['value']}"
    labelled = [light(str(e["value"])) for e in ents]
    for raw, keys in known:
        if _contains(keys, after) and not _contains(keys, before) \
                and not any(light(raw) == lab or same_name(raw, lab) or name_present(raw, lab) for lab in labelled):
            return "damage", "invented_entity"
    if any(u.is_number for u in before + after):
        if _facts(before) == _facts(after):
            return "format", "number_format"
        return "damage", "value_changed"
    if bt and at and same_name(bt, at):
        return "format", "same_sound"
    return "damage", "rewrite"


def flag_refers_to(surface: str, output_text: str, reference: str, truth: str) -> bool:
    """Does the flagged span of the output sit where the reference states `truth`? Aligned on shared words around it."""
    out, ref, span = segment(output_text), segment(reference), segment(surface)
    keys, wanted = [_sound_key(u) for u in out], [_sound_key(u) for u in span]
    at = next((i for i in range(len(keys) - len(wanted) + 1) if keys[i:i + len(wanted)] == wanted), None) if wanted else None
    if at is None:
        return False
    low, high = 0, len(ref)
    for block in SequenceMatcher(None, keys, [_sound_key(u) for u in ref], autojunk=False).get_matching_blocks():
        if block.size and block.a <= at and at + len(wanted) <= block.a + block.size:
            low, high = block.b + at - block.a, block.b + at - block.a + len(wanted)   # the span itself is aligned
            break
        if block.size and block.a + block.size <= at:
            low = block.b + block.size
        elif block.size and block.a >= at + len(wanted):
            high = block.b
            break
    return name_present(truth, " ".join(u.surface for u in ref[low:high]))


def _sound_key(unit: Unit) -> str:
    return unit.key if unit.is_number else (phon(unit.surface)[0] or unit.key)


def audit_edits(input_text: str, output_text: str, entities: list[dict],
                known_names: Iterable[str]) -> list[dict]:
    """Classify every changed chunk between input_text and output_text."""
    a, b = segment(input_text), segment(output_text)
    known = []
    for raw in dict.fromkeys(known_names):
        keys = tuple(light(u.surface) for u in segment(raw))
        if keys:
            known.append((raw, keys))
    out: list[dict] = []
    sm = SequenceMatcher(None, [u.key for u in a], [u.key for u in b], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        before, after = a[i1:i2], b[j1:j2]
        if op == "equal":
            for x, y in zip(before, after, strict=True):
                if x.is_number and x.surface.replace(" ", "") != y.surface.replace(" ", ""):
                    out.append({"kind": "format", "reason": "number_format",
                                "before": x.surface, "after": y.surface})
            continue
        kind, reason = _classify(before, after, entities, known)
        out.append({"kind": kind, "reason": reason,
                    "before": " ".join(u.surface for u in before),
                    "after": " ".join(u.surface for u in after)})
    return out
