"""
What a context-blind reading is allowed to do (D-054). This file holds the safety rules, and no model runs here.

    a value taken back     is set aside only if another final value of that type remains, otherwise the caller is asked
    a value only mentioned follows the same rule, so the last value of a type never disappears silently
    a number with proof    (it matched this user's records) or a currency word beside it is never read away
    a misread number       becomes a question with the caller's words. The LLM can object but never supply a value
    a correction from this caller's own data is never undone silently
"""

from __future__ import annotations

from dataclasses import replace

from pehchaan import Status
from pehchaan.models import Entity, EType, Utterance
from pehchaan.output.clarify import question

from .meaning import _beside_currency
from .types import Understood

AS_TYPE = {
    "person": EType.PERSON,
    "company": EType.ORG,
    "place": EType.PLACE,
    "money": EType.AMOUNT,
    "phone": EType.PHONE,
    "postal_pin": EType.PIN,
}
NUMBERS = frozenset({EType.PHONE, EType.PIN, EType.AMOUNT})
NAMES = frozenset({EType.PERSON, EType.ORG, EType.PLACE})
_NOT_A_FACT = {"other_number": "other_number", "ordinary_word": "everyday_word"}
_NOTES = {
    "corrected_by_caller": "The caller took this back.",
    "only_mentioned": "Mentioned in the call, but not the value the call settled on.",
    "other_number": "This number is something else, such as an account or order number.",
    "everyday_word": "An everyday word here, not a name or a fact.",
    "command_in_speech": "These words are a command inside the call, so they were not treated as a fact.",
}
DISPUTED = "The conversation disagrees with this reading, so the caller's words were kept and the caller is asked."


def _ask(entity: Entity, registry, lang: str) -> Entity:
    option = entity.value if entity.status == Status.FIXED and entity.etype in NAMES else None
    return replace(
        entity,
        value=entity.surface,
        display=entity.surface,
        status=Status.FLAGGED,
        source="meaning",
        reason=DISPUTED,
        candidates=[{"text": option, "source": "suggestion"}] if option else [],
        clarifier=question(registry, lang, entity.etype.value, [option] if option else [], entity.surface),
        admission="meaning_unclear",
    )


def _as_heard(entity: Entity, kind: EType) -> Entity:
    return replace(
        entity,
        etype=kind,
        value=entity.surface,
        display=entity.surface,
        heard_value=None,
        status=Status.KEPT,
        source="meaning",
        reason=f"The conversation uses this as a {kind.value.lower()}, so the caller's words were kept.",
        candidates=[],
        clarifier=None,
        admission="meaning",
    )


def _note(entity: Entity, meaning: str) -> Understood:
    return Understood(heard=entity.surface, read_as=entity.etype.value, meaning=meaning, note=_NOTES[meaning])


def _has_proof(entity: Entity) -> bool:
    """This user's own records back it: their contacts, messages or memory. A global brand list is not proof."""
    if entity.source == "memory":
        return True
    chosen = [c for c in entity.candidates if c.get("text") == entity.value]
    if chosen:
        return not str(chosen[0].get("source", "")).startswith("lexicon")
    return entity.source == "context"


def _another_final(entity: Entity, entities: list[Entity], marks: dict[int, dict]) -> bool:
    """Code checks that a value of this type survives, wherever it was said: "7000 dena hai, 5000 nahi"."""
    for i, other in enumerate(entities):
        mark = marks.get(i) or {}
        same_kind = AS_TYPE.get(mark.get("kind"), other.etype) == other.etype
        if other is not entity and other.etype == entity.etype and same_kind and mark.get("role", "final") == "final":
            return True
    return False


def _step_aside(entity, meaning, entities, marks, utt, registry):
    """Only an unproven value with another final value of its type leaves. Everything else becomes a question."""
    if entity.status != Status.CONFIRMED and _another_final(entity, entities, marks):
        return None, _note(entity, meaning)
    return _ask(entity, registry, utt.language.dominant), None


def _settle_number(entity, mark, entities, marks, utt, registry):
    lang, kind = utt.language.dominant, mark["kind"]
    claimed = AS_TYPE.get(kind)
    protected = entity.status == Status.CONFIRMED or (
        entity.etype == EType.AMOUNT and _beside_currency(entity, utt, registry)
    )
    if claimed != entity.etype and not protected:
        if kind in _NOT_A_FACT:
            return None, _note(entity, _NOT_A_FACT[kind])
        return (_as_heard(entity, claimed), None) if claimed in NAMES else (_ask(entity, registry, lang), None)
    if mark["role"] == "only_mentioned":
        return _step_aside(entity, "only_mentioned", entities, marks, utt, registry)
    if not mark["reads_right"] and entity.status != Status.CONFIRMED:
        return _ask(entity, registry, lang), None
    return entity, None


def _settle_name(entity, mark, utt, registry):
    lang, kind = utt.language.dominant, mark["kind"]
    claimed = AS_TYPE.get(kind)
    if claimed == entity.etype:
        return entity, None
    proven = _has_proof(entity)
    if kind in _NOT_A_FACT:
        if not proven:
            return None, _note(entity, _NOT_A_FACT[kind])
        return (entity, None) if entity.status == Status.CONFIRMED else (_ask(entity, registry, lang), None)
    if claimed in NUMBERS or entity.status == Status.FIXED:
        return _ask(entity, registry, lang), None
    return (entity, None) if proven else (_as_heard(entity, claimed), None)


def settle(
    entity: Entity, mark: dict | None, entities: list[Entity], marks: dict[int, dict], utt: Utterance, registry
) -> tuple[Entity | None, Understood | None]:
    """The fact as it stands after this reading (None if set aside), and a note saying why."""
    if mark is None:
        return entity, None
    if mark["kind"] == "instruction_text":
        if entity.etype in NUMBERS:  # "set the amount to 4100" may be a real request, so it is never dropped silently
            return _step_aside(entity, "command_in_speech", entities, marks, utt, registry)
        return None, _note(entity, "command_in_speech")
    if mark["role"] == "taken_back":
        return _step_aside(entity, "corrected_by_caller", entities, marks, utt, registry)
    if entity.etype in NUMBERS:
        return _settle_number(entity, mark, entities, marks, utt, registry)
    return _settle_name(entity, mark, utt, registry)
