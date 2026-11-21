"""
AdmissionGate: the one place that enforces what a correction is allowed to do.

A resolver's output is a proposal. Every proposal passes these rules before it can change the transcript, so a bug
in any resolver (or a wrong LLM answer) cannot break a safety promise:

  critical_read_only   PHONE / PIN / AMOUNT keep the value that was heard. A proposed change becomes a question.
  acronym_spelled      "LIC" needs the letters L-I-C. The word "लिख" sounding similar is not evidence.
  common_word          An everyday word ("delivery") stays a word unless this call's context names that entity AND
                       the word sits where an entity belongs ("Delhivery se ...").
  person_not_place     A span marked as a place ("... wale") cannot become a person from the contact list.
  second_opinion       The context-biased transcript can echo a context entry that was never said. If a transcript
                       made WITHOUT context heard neither that name nor that number, we ask instead of confirming.
                       If it heard the same number, a mere resemblance to a context number is not worth a question.
  known_name_heard     A learned correction repairs a mishearing. It cannot overwrite a real, known name unless a
                       transcript made without context shows that name was never said.

Refused proposals are returned with their rule, so every decision can be inspected and explained.
"""
from __future__ import annotations

from dataclasses import replace

from ..config import settings
from ..context import CallContext, lexicon
from ..languages import LanguageRegistry
from ..models import Entity, EType, Status, Utterance
from ..output import question
from ..sound import consonant_changes, key, phrase_distance, word_keys
from .second_opinion import SecondOpinion

NAME_TYPES = frozenset({EType.PERSON, EType.ORG, EType.PLACE})
PER_CALL_SOURCES = frozenset({"contacts", "caller_id", "sms", "saved_places"})


class AdmissionGate:
    def __init__(self, registry: LanguageRegistry):
        self.registry = registry
        self.critical = frozenset(EType(t) for t in settings()["decisions"]["critical_types"])
        self.acronym_max_letters = settings()["policy"]["acronym_max_letters"]
        self.same_sound = settings()["matching"]["verify_max_dist"]

    def review(self, proposals: list[Entity], utt: Utterance,
               second_opinion: SecondOpinion | None = None,
               ctx: CallContext | None = None) -> tuple[list[Entity], list[dict]]:
        """Returns (admitted entities, refusal records)."""
        admitted, refused = [], []
        for proposal in proposals:
            if proposal.etype in self.critical:
                entity = self._read_only(proposal, utt)
                entity = self._number_cross_check(entity, utt, second_opinion)
                if entity.admission != "admitted":
                    refused.append(_record(proposal, entity.admission))
                admitted.append(entity)
                continue
            rule = self._refusal_rule(proposal, utt, second_opinion, ctx) if proposal.etype in NAME_TYPES else None
            if rule:
                refused.append(_record(proposal, rule))
                continue
            entity = self._name_cross_check(proposal, utt, second_opinion)
            if entity.admission != "admitted":
                refused.append(_record(proposal, entity.admission))
            admitted.append(entity)
        return admitted, refused

    # ---- second opinion ------------------------------------------------------------------------
    def _number_cross_check(self, e: Entity, utt: Utterance, opinion: SecondOpinion | None) -> Entity:
        if opinion is None:
            return e
        if e.status == Status.FLAGGED and e.source == "context" and opinion.heard_number(e):
            return replace(e, status=Status.KEPT, candidates=[], clarifier=None, admission="admitted",
                           reason="near a context number, but a context-free transcript heard the same value")
        if e.status != Status.KEPT or opinion.heard_number(e):
            return e
        other = opinion.nearest_number(e)
        options = [{"text": other, "source": "second_transcript"}] if other else []
        asked = question(self.registry, utt.language.dominant, e.etype.value, [e.display], e.surface)
        return replace(e, display=e.surface, status=Status.FLAGGED, candidates=options + e.candidates, clarifier=asked,
                       admission="second_opinion", reason="two independent transcripts disagree on this number")

    def _name_cross_check(self, e: Entity, utt: Utterance, opinion: SecondOpinion | None) -> Entity:
        if opinion is None or e.source not in ("context", "lexicon", "llm") or e.status == Status.FLAGGED:
            return e
        if self._is_different_name(e) and opinion.prefers_heard(e.surface, e.value):
            names = [e.surface, e.value]
            asked = question(self.registry, utt.language.dominant, e.etype.value, names, e.surface)
            options = [{"text": e.surface, "source": "second_transcript"}, {"text": e.value, "source": e.source}]
            return replace(e, value=e.surface, display=e.surface, status=Status.FLAGGED, candidates=options,
                           clarifier=asked, admission="second_opinion",
                           reason=f"both transcripts heard '{e.surface}', so '{e.value}' from context is only a look-alike")
        if opinion.heard_name(e.value):
            return e
        asked = question(self.registry, utt.language.dominant, e.etype.value, [e.value], e.surface)
        options = e.candidates or [{"text": e.value, "source": e.source}]
        return replace(e, value=e.surface, display=e.surface, status=Status.FLAGGED, candidates=options, clarifier=asked,
                       admission="second_opinion",
                       reason=f"'{e.value}' may be an echo of the context: a transcript made without context did not hear it")

    def _is_different_name(self, e: Entity) -> bool:
        """Mishearings keep the consonants or swap similar ones. An unrelated consonant means another name.
        People are held to a stricter standard: one added or lost consonant is already a different person."""
        if (e.distance or 0.0) <= self.same_sound:
            return False
        swaps, gaps = consonant_changes(e.surface, e.value)
        return swaps > 0 or (e.etype == EType.PERSON and gaps > 0)

    # ---- critical facts ------------------------------------------------------------------------
    def _read_only(self, e: Entity, utt: Utterance) -> Entity:
        if e.heard_value is None:
            raise ValueError(f"{e.etype.value} proposal from '{e.source}' must state heard_value")
        if e.status != Status.FIXED and e.value == e.heard_value:
            return e
        options = [{"text": e.display, "source": e.source}] if e.value != e.heard_value else []
        options += [c for c in e.candidates if c.get("text") != e.display]
        asked = question(self.registry, utt.language.dominant, e.etype.value, [o["text"] for o in options[:1]], e.surface)
        return replace(e, value=e.heard_value, display=e.surface, status=Status.FLAGGED, candidates=options,
                       clarifier=asked, admission="critical_read_only",
                       reason=f"{e.reason} (not applied: {e.etype.value} is never changed without asking)")

    # ---- names ---------------------------------------------------------------------------------
    def _refusal_rule(self, e: Entity, utt: Utterance, opinion: SecondOpinion | None,
                      ctx: CallContext | None) -> str | None:
        if e.source == "memory":
            return "known_name_heard" if self._erases_real_name(e, opinion, ctx) else None
        if not self._acronym_is_spelled(e, utt):
            return "acronym_spelled"
        if self._is_common_word_span(e, utt) and not (self._has_call_evidence(e) and self._in_entity_position(e, utt)):
            return "common_word"
        if e.etype == EType.PERSON and e.status != Status.FLAGGED and self._followed_by(e, utt, "place_after"):
            return "person_not_place"
        return None

    def _erases_real_name(self, e: Entity, opinion: SecondOpinion | None, ctx: CallContext | None) -> bool:
        heard = word_keys(e.surface)
        names = {*lexicon.all_names(), *(c.output for c in ctx.candidates)} if ctx else set(lexicon.all_names())
        is_real = bool(heard) and any(key(n) != key(e.value) and phrase_distance(heard, word_keys(n)) <= self.same_sound
                                      for n in names)
        return is_real and (opinion is None or opinion.heard_name(e.surface))

    def _acronym_is_spelled(self, e: Entity, utt: Utterance) -> bool:
        brand = lexicon.brand_by_name(e.value) if e.etype == EType.ORG else None
        if e.etype != EType.ORG or (brand is not None and brand.spoken_as_word):
            return True
        head = e.value.split()[0]
        if not (head.isascii() and head.isupper() and 2 <= len(head) <= self.acronym_max_letters):
            return True
        target, heard = head.lower(), ""
        for token in utt.tokens[e.start_tok:e.end_tok]:
            heard += token.norm
            if heard == target or self.registry.decode_spelled_acronym(heard, min_letters=2) == target:
                return True
        return False

    def _is_common_word_span(self, e: Entity, utt: Utterance) -> bool:
        tokens = utt.tokens[e.start_tok:e.end_tok]
        if len(tokens) > 1 and (e.distance or 0.0) <= self.same_sound:
            return False                               # a whole phrase matching exactly ("Yes Bank") is not a coincidence
        return all(self.registry.is_common(t.norm) for t in tokens)

    @staticmethod
    def _has_call_evidence(e: Entity) -> bool:
        return any(c.get("text") == e.value and c.get("source") in PER_CALL_SOURCES for c in e.candidates)

    def _in_entity_position(self, e: Entity, utt: Utterance) -> bool:
        if self._followed_by(e, utt, "origin_after"):
            return True
        return e.start_tok > 0 and utt.tokens[e.start_tok - 1].norm in self.registry.marker_words("origin_before")

    def _followed_by(self, e: Entity, utt: Utterance, marker: str) -> bool:
        return e.end_tok < len(utt.tokens) and utt.tokens[e.end_tok].norm in self.registry.marker_words(marker)


def _record(e: Entity, rule: str) -> dict:
    return {"rule": rule, "etype": e.etype.value, "surface": e.surface, "proposed": e.display,
            "proposed_status": e.status.value, "source": e.source}
