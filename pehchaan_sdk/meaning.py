"""
Does the conversation actually mean this? A check on the frozen engine's answer (D-051).

The engine reads "koti" as ten million wherever it appears, and reports a word even after its judge rejected every
candidate for it. Neither decision looks at what the caller is talking about, so this layer does:

    a lone number word with no count   -> an LLM reads the whole call: money, person, place, or an everyday word
    a correction from a global list    -> the same LLM read checks that the caller meant that brand or place
    a candidate the judge turned down  -> not a fact, so it is not reported

It can only take a reading away, and the caller's words then stay as spoken. It never writes or changes a value.
With no LLM, or when it fails, number words stay as said (a nearby money word raises a question) and corrections stand.
A disputed correction is never settled silently: the caller's words stay and the caller is asked.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, replace

from pehchaan import Result, Status
from pehchaan.config import settings
from pehchaan.languages import get_registry
from pehchaan.models import Entity, EType, Utterance
from pehchaan.output.clarify import question
from pehchaan.output.rewrite import rewrite_with_spans
from pehchaan.text.normalize import CLAUSE_BREAKS
from pehchaan.utterance import build_utterance

_logger = logging.getLogger(__name__)
_NAMES = frozenset({"PERSON", "ORG", "PLACE"})
_AS_FACT = {"person": EType.PERSON, "place": EType.PLACE}
MEANINGS = ("money", "person", "place", "other", "unsure")
UNCLEAR = "This word can be a number or a name, and the call does not settle it, so the caller's words were kept."

SYSTEM_PROMPT = (
    "You read one phone-call transcript from India. It may mix Hindi, Telugu, English and other languages. "
    "Some words are marked [[n: word]]. Each one can mean a large number, but the same word can also be a person's "
    "name, a place, or part of an everyday expression. A mark written [[n: word | suggested: name]] means a list of "
    "known names proposes that the speech model misheard that name. Use the whole conversation to decide what the "
    "speaker meant. The meaning always describes the word as written.\n"
    "money: a sum of money, or the price, cost or value of something, even when no currency word is said.\n"
    "person: the name of a person, including a relative or friend the speaker is talking about.\n"
    "place: the name of an area, town, road or landmark.\n"
    "other: an everyday expression or anything else, such as saying something was done a thousand times.\n"
    "unsure: the conversation does not settle it.\n"
    "same_as_suggestion: true if the marked word and the suggestion are the same real thing, even when written in "
    "another script, spelled differently, shortened, or slightly misheard. False if the word is a different real "
    "thing, such as a city mistaken for a company, or an ordinary word in the sentence. False when there is no "
    "suggestion.\n"
    "Never answer money only because the word is a number word. Give a reason of at most 12 English words."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "readings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "meaning": {"type": "string", "enum": list(MEANINGS)},
                    "same_as_suggestion": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "meaning", "same_as_suggestion", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["readings"],
    "additionalProperties": False,
}


class MeaningReader:
    """One LLM call that reads every doubtful word in its conversation. Runs on the caller's key."""

    def __init__(self, client):
        self.client = client
        self.model = settings()["sdk"]["meaning_model"]
        self.timeout_s = settings()["sdk"]["meaning_timeout_s"]
        self.requests = 0

    def read(self, text: str, words: list[str]) -> dict[int, dict]:
        self.requests += 1
        reply = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "word_meanings", "strict": True, "schema": SCHEMA},
            },
            timeout=self.timeout_s,
        )
        readings = json.loads(reply.choices[0].message.content)["readings"]
        return {r["id"]: r for r in readings if 0 <= r["id"] < len(words) and r["meaning"] in MEANINGS}


@dataclass(frozen=True)
class MeaningCheck:
    changed: bool
    calls: int


def is_rejected(fact: dict) -> bool:
    """A name-type fact the judge kept only because it turned down every candidate. No evidence says it is a fact."""
    return fact.get("etype") in _NAMES and fact.get("status") == "KEPT" and fact.get("source") == "llm"


def without_rejected(value):
    """The same packaged answer with rejected facts left out. Text and measured counts are not touched."""
    if isinstance(value, list):
        return [without_rejected(item) for item in value if not (isinstance(item, dict) and is_rejected(item))]
    if isinstance(value, dict):
        return {key: without_rejected(item) for key, item in value.items()}
    return value


def _is_lone(entity: Entity, utt: Utterance, registry) -> bool:
    """Only a multiplier with nothing counting it: "koti" is doubtful, "ek koti" and "2 lakh" are not."""
    tokens = utt.tokens[entity.start_tok : entity.end_tok]
    return entity.etype == EType.AMOUNT and all(
        not t.norm.isdigit() and registry.multiplier(t.norm) is not None for t in tokens
    )


def _from_global_list(entity: Entity) -> bool:
    """A judge's pick from a big brand or place list. Close sound matches and this call's contacts are not in doubt."""
    if entity.status != Status.FIXED or entity.source != "llm" or entity.etype.value not in _NAMES:
        return False
    chosen = [c for c in entity.candidates if c.get("text") == entity.value]
    return bool(chosen) and str(chosen[0].get("source", "")).startswith("lexicon")


def _same_clause(utt: Utterance, a: int, b: int) -> bool:
    return not any(ch in CLAUSE_BREAKS for ch in utt.text[utt.tokens[a].end : utt.tokens[b].start])


def _beside_currency(entity: Entity, utt: Utterance, registry) -> bool:
    """ "koti rupaye" needs no LLM: the word right beside it says this is money."""
    words = registry.cue_words("CURRENCY")
    before, after = entity.start_tok - 1, entity.end_tok
    return (before >= 0 and utt.tokens[before].norm in words and _same_clause(utt, before, entity.start_tok)) or (
        after < len(utt.tokens) and utt.tokens[after].norm in words and _same_clause(utt, entity.end_tok - 1, after)
    )


def _near_money_word(entity: Entity, utt: Utterance, registry) -> bool:
    cfg, words = settings()["numbers"], registry.cue_words("AMOUNT") | registry.cue_words("CURRENCY")
    first = max(0, entity.start_tok - cfg["cue_window_before"])
    last = min(len(utt.tokens), entity.end_tok + cfg["cue_window_after"])
    return any(utt.tokens[i].norm in words for i in range(first, last) if not entity.start_tok <= i < entity.end_tok)


def _marked(utt: Utterance, doubtful: list[Entity]) -> str:
    text, cursor, parts = utt.text, 0, []
    for number, entity in enumerate(doubtful):
        start, end = utt.tokens[entity.start_tok].start, utt.tokens[entity.end_tok - 1].end
        hint = f" | suggested: {entity.value}" if entity.status == Status.FIXED else ""
        parts += [text[cursor:start], f"[[{number}: {text[start:end]}{hint}]]"]
        cursor = end
    return "".join([*parts, text[cursor:]])


def _ask(entity: Entity, registry, lang: str) -> Entity:
    return replace(
        entity,
        value=entity.surface,
        display=entity.surface,
        heard_value=entity.surface,
        status=Status.FLAGGED,
        source="meaning",
        reason=UNCLEAR,
        candidates=[],
        clarifier=question(registry, lang, "AMOUNT", [], entity.surface),
        admission="meaning_unclear",
    )


def _ask_which(entity: Entity, registry, lang: str) -> Entity:
    return replace(
        entity,
        value=entity.surface,
        display=entity.surface,
        status=Status.FLAGGED,
        source="meaning",
        reason=f"'{entity.value}' was suggested, but the conversation does not support it, so the words were kept",
        candidates=[{"text": entity.value, "source": "suggestion"}],
        clarifier=question(registry, lang, entity.etype.value, [entity.value], entity.surface),
        admission="meaning_unclear",
    )


def _as_said(entity: Entity, kind: EType, why: str) -> Entity:
    label = "a person's name" if kind == EType.PERSON else "a place"
    return replace(
        entity,
        etype=kind,
        value=entity.surface,
        display=entity.surface,
        heard_value=None,
        status=Status.KEPT,
        source="meaning",
        reason=f"the conversation uses this as {label}: {why}",
        candidates=[],
        clarifier=None,
        admission="meaning",
    )


def _settle(entity: Entity, reading: dict | None, utt: Utterance, registry) -> Entity | None:
    """The fact to report for one doubtful word. None means it is not a fact."""
    lang = utt.language.dominant
    if entity.status == Status.FIXED:  # the engine's correction stands unless the conversation disputes it
        if reading is None or reading.get("same_as_suggestion"):
            return entity
        return _ask_which(entity, registry, lang)  # never pick a side silently: the caller settles it
    if reading is None:
        return _ask(entity, registry, lang) if _near_money_word(entity, utt, registry) else None
    meaning = reading["meaning"]
    if meaning == "money":
        return entity
    if meaning in _AS_FACT:
        return _as_said(entity, _AS_FACT[meaning], reading.get("reason", ""))
    return _ask(entity, registry, lang) if meaning == "unsure" else None


def check_meaning(result: Result, reader=None) -> MeaningCheck:
    """Correct `result` in place. When nothing is doubtful, it stays exactly what the frozen engine returned."""
    started = time.perf_counter()
    registry = get_registry()
    utt = build_utterance(result.text_in, registry, None)
    doubtful = [
        e
        for e in result.entities
        if _from_global_list(e)
        or (e.admission != "no_number_rules" and _is_lone(e, utt, registry) and not _beside_currency(e, utt, registry))
    ]
    readings: dict[int, dict] = {}
    calls = 0
    if doubtful and reader is not None:
        calls = 1
        try:
            readings = reader.read(_marked(utt, doubtful), [e.surface for e in doubtful])
        except Exception as exc:  # noqa: BLE001 - an outage must never break a call
            _logger.warning("the meaning check failed (%s)", type(exc).__name__)
    settled = {id(e): _settle(e, readings.get(i), utt, registry) for i, e in enumerate(doubtful)}
    kept = [settled.get(id(e), e) for e in result.entities if not is_rejected(e.to_dict())]
    entities = [e for e in kept if e is not None]
    changed = len(entities) != len(result.entities) or any(
        a is not b for a, b in zip(entities, result.entities, strict=False)
    )
    if changed:
        result.entities = entities
        result.text_out, result.spans = rewrite_with_spans(utt, entities, registry)
        result.questions = [
            {"entity": i, "etype": e.etype.value, "question": e.clarifier}
            for i, e in enumerate(entities)
            if e.status == Status.FLAGGED and e.clarifier
        ]
    if calls or changed:
        spent = round((time.perf_counter() - started) * 1000, 2)
        result.timings_ms["meaning"] = spent
        result.timings_ms["total"] = round(result.timings_ms["total"] + spent, 2)
    return MeaningCheck(changed, calls)
