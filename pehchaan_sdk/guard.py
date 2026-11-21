"""
A safety net around the frozen engine for languages it has no number rules for.

Without rules, a word like "બે હજાર" (two thousand) can be half-read as 1,000. Money and phone numbers must never change
on a guess, so any number spoken in such a language keeps the caller's words and becomes a question. Hindi, Hinglish,
English and Telugu have number rules, so this never touches them and the measured exam setup is unaffected.
"""

from __future__ import annotations

from dataclasses import replace

from pehchaan import Result, Status
from pehchaan.languages import get_registry
from pehchaan.output.clarify import question
from pehchaan.text import script_of

NUMBERS = frozenset({"PHONE", "PIN", "AMOUNT"})
MIXED_CODES = {"hl": "hi"}  # Hinglish uses the Hindi and English packs
REASON = "This language has no number rules yet, so the caller's words were kept and need confirming."


def has_number_rules(language: str | None) -> bool:
    if not language:
        return True
    code = language.split("-")[0].lower()
    return MIXED_CODES.get(code, code) in get_registry().packs


def speech_hint(language: str | None) -> str | None:
    """The code a speech model understands. Hinglish is not a code, so it keeps the default language hints."""
    if not language:
        return None
    code = language.split("-")[0].lower()
    return None if code in MIXED_CODES else code


def _owned_scripts() -> set[str]:
    return {script for pack in get_registry().packs.values() for script in pack.scripts}


def _unreadable(surface: str, language: str | None, owned: set[str]) -> bool:
    if any((script := script_of(ch)) and script not in owned for ch in surface):
        return True
    return not has_number_rules(language) and any(ch.isalpha() for ch in surface)


def protect_numbers(result: Result, language: str | None = None) -> bool:
    """Restore and flag numbers the engine cannot safely read. Returns True if it changed anything."""
    owned, registry, text, changed = _owned_scripts(), get_registry(), result.text_out, False
    order = sorted(result.spans, key=lambda i: result.spans[i]["start"], reverse=True)
    for index in order:
        entity = result.entities[index]
        if entity.etype.value not in NUMBERS or not _unreadable(entity.surface, language, owned):
            continue
        span = result.spans[index]
        words = result.text_in[span["input_start"] : span["input_end"]]
        text = text[: span["start"]] + words + text[span["end"] :]
        ask = question(registry, "en", entity.etype.value, [], entity.surface)
        result.entities[index] = replace(
            entity,
            value=entity.surface,
            display=words,
            status=Status.FLAGGED,
            reason=REASON,
            candidates=[],
            clarifier=ask,
            admission="no_number_rules",
        )
        changed = True
    result.text_out = text
    return changed
