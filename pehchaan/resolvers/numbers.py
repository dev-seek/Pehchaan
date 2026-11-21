"""
NumberResolver: phone numbers, PIN codes and amounts.

Steps per number run:
 1. decide its KIND from validity and nearby cue words ("number", "pin", "rupaye", "EMI") in any active language
 2. compare the heard value with the rules and with what the phone knows

Policy (DECISIONS D-021): a number is READ-ONLY. Context can confirm it or raise a question, never replace it.
Likely repairs are offered as options in the question. `policy.AdmissionGate` enforces this for every resolver.
"""

from __future__ import annotations

from collections.abc import Callable

from ..config import settings
from ..context import CallContext, lexicon
from ..languages import LanguageRegistry
from ..models import Entity, EType, Status, Utterance
from ..numbers import NumberRun, find_runs, rules
from ..output import question
from ..text.normalize import CLAUSE_BREAKS


class NumberResolver:
    name = "numbers"

    def __init__(self, registry: LanguageRegistry):
        self.registry = registry
        self.cfg = settings()
        self.n = self.cfg["numbers"]
        self._rules: dict[EType, Callable[..., Entity | None]] = {
            EType.PHONE: self._phone,
            EType.PIN: self._pin,
            EType.AMOUNT: self._amount,
        }

    def resolve(self, utt: Utterance, ctx: CallContext, claimed: set[int]) -> list[Entity]:
        out = []
        for run in find_runs(utt.tokens, self.registry):
            if any(i in claimed for i in range(run.start, run.end)):
                continue
            etype = self._kind_of(run, utt)
            if etype is None:
                continue  # "5 baje", "2 din": not a fact we take responsibility for
            base = dict(
                etype=etype,
                surface=utt.span_text(run.start, run.end),
                start_tok=run.start,
                end_tok=run.end,
                asr_confidence=utt.min_confidence(run.start, run.end),
            )
            entity = self._rules[etype](run, ctx, utt, base)
            if entity:
                out.append(entity)
        return out + self._unreadable_after_cue(utt, claimed, out)

    # ---- kind ----------------------------------------------------------------------------------
    def _cue_distance(self, utt: Utterance, run: NumberRun, kind: str) -> int | None:
        words = self.registry.cue_words(kind)
        best = None
        first = max(0, run.start - self.n["cue_window_before"])
        for i in range(first, min(len(utt.tokens), run.end + self.n["cue_window_after"])):
            if not (run.start <= i < run.end) and utt.tokens[i].norm in words:
                d = run.start - i if i < run.start else i - (run.end - 1)
                best = d if best is None else min(best, d)
        return best

    def _kind_of(self, run: NumberRun, utt: Utterance) -> EType | None:
        cue = {k: self._cue_distance(utt, run, k) for k in ("PHONE", "PIN", "AMOUNT")}
        digits = rules.strip_phone_prefix(run.digit_reading)

        def closer(kind: str, other: str) -> bool:
            return cue[kind] is not None and (cue[other] is None or cue[kind] <= cue[other])

        if rules.is_mobile(digits) and not (run.has_multiplier and closer("AMOUNT", "PHONE")):
            return EType.PHONE
        if (
            not run.has_multiplier
            and len(run.digit_reading) >= self.n["pin_min_digits_when_cued"]
            and closer("PIN", "AMOUNT")
        ):
            return EType.PIN
        if run.has_multiplier or closer("AMOUNT", "PHONE"):
            return EType.AMOUNT
        if cue["PHONE"] is not None and len(digits) >= self.n["phone_min_digits_when_cued"]:
            return EType.PHONE
        return EType.AMOUNT if cue["AMOUNT"] is not None else None

    def _ask(self, utt: Utterance, etype: str, options: list[str], heard: str) -> str:
        return question(self.registry, utt.language.dominant, etype, options, heard)

    def _asr_sure(self, conf: float | None) -> bool:
        return conf is not None and conf >= self.cfg["matching"]["low_conf_logprob"]

    def _flag(
        self, utt: Utterance, base: dict, value: str, display: str, why: str, options: list[str], source: str = "rule"
    ) -> Entity:
        return Entity(
            value=value,
            heard_value=value,
            display=display,
            status=Status.FLAGGED,
            source=source,
            reason=why,
            candidates=[{"text": x, "source": "suggestion"} for x in options],
            clarifier=self._ask(utt, base["etype"].value, options[:1], display),
            **base,
        )

    # ---- PHONE ---------------------------------------------------------------------------------
    def _phone(self, run: NumberRun, ctx: CallContext, utt: Utterance, base: dict) -> Entity:
        d = rules.strip_phone_prefix(run.digit_reading)
        fmt = rules.format_phone
        max_edits = self.n["phone_context_max_digit_edits"]
        near = sorted(p for p in ctx.phones if p != d and rules.digit_edit_distance(d, p) <= max_edits)
        if rules.is_mobile(d):
            if d in ctx.phones:
                return Entity(
                    value=d,
                    heard_value=d,
                    display=fmt(d),
                    status=Status.CONFIRMED,
                    source="context",
                    reason="matches a number already on this phone (caller ID / contacts / SMS)",
                    **base,
                )
            if near and not self._asr_sure(base["asr_confidence"]):
                return self._flag(
                    utt,
                    base,
                    d,
                    fmt(d),
                    f"valid number, but one digit away from known {fmt(near[0])}",
                    [fmt(p) for p in near[:2]],
                    source="context",
                )
            return Entity(
                value=d,
                heard_value=d,
                display=fmt(d),
                status=Status.KEPT,
                source="rule",
                reason="valid Indian mobile number (10 digits, starts 6-9)",
                **base,
            )
        repairs = sorted(r for r in rules.stutter_repairs(d) if rules.is_mobile(r)) if len(d) == 11 else []
        options = list(dict.fromkeys([fmt(p) for p in near] + [fmt(r) for r in repairs]))[:2]
        return self._flag(utt, base, d, d, f"{len(d)} digits is not a valid Indian mobile number", options)

    # ---- PIN -----------------------------------------------------------------------------------
    def _pin(self, run: NumberRun, ctx: CallContext, utt: Utterance, base: dict) -> Entity:
        d = run.digit_reading
        prefixes = lexicon.pin_prefixes(ctx.city) if self.n["pin_check_city_prefix"] else []

        def valid(p: str) -> bool:
            return rules.is_valid_pin(p, prefixes)

        if valid(d):
            known = d in ctx.pins
            why = (
                "matches a PIN on this phone"
                if known
                else (f"valid PIN for {ctx.city}" if prefixes else "valid 6-digit PIN")
            )
            return Entity(
                value=d,
                heard_value=d,
                display=d,
                status=Status.CONFIRMED if known else Status.KEPT,
                source="context" if known else "rule",
                reason=why,
                **base,
            )
        near = sorted(p for p in ctx.pins if rules.digit_edit_distance(d, p) <= 1)
        doubled = sorted(r for r in rules.stutter_repairs(d) if valid(r)) if len(d) == 7 else []
        dropped = sorted(r for r in rules.single_deletions(d) if valid(r)) if len(d) == 7 else []
        options = list(dict.fromkeys(near + doubled + dropped))[:2]  # likeliest repair first: a doubled digit
        return self._flag(
            utt, base, d, d, f"'{d}' is not a valid PIN" + (f" for {ctx.city}" if prefixes else ""), options
        )

    # ---- AMOUNT --------------------------------------------------------------------------------
    def _amount(self, run: NumberRun, ctx: CallContext, utt: Utterance, base: dict) -> Entity | None:
        v = (
            run.value_reading
            if run.value_reading is not None
            else (float(run.digit_reading) if run.digit_reading else None)
        )
        if v is None or v <= 0:
            return None
        inr, value = rules.format_inr, rules.plain_amount(v)
        if self._count_is_unreadable(run, utt):
            return self._flag(
                utt, base, value, base["surface"], "the word before this amount may be a number we could not read", []
            )
        if v in ctx.amounts:
            return Entity(
                value=value,
                heard_value=value,
                display=inr(v),
                status=Status.CONFIRMED,
                source="context",
                reason="matches an amount in this user's SMS",
                **base,
            )
        alternatives = list(run.teen_ty_alternatives)
        if len(run.words) == 1 and run.words[0].isdigit():
            alternatives += [float(x) for x in rules.teen_ty_digit_variants(run.words[0])]
        hits = [a for a in alternatives if a in ctx.amounts]
        if hits:
            return self._flag(
                utt,
                base,
                value,
                inr(v),
                f"heard {inr(v)} but SMS says {inr(hits[0])} (teen/ty confusion)",
                [inr(hits[0])],
                source="context",
            )
        return Entity(
            value=value,
            heard_value=value,
            display=inr(v),
            status=Status.KEPT,
            source="rule",
            reason="amount read with Indian number rules (lakh/hazaar/saade...)",
            **base,
        )

    def _count_is_unreadable(self, run: NumberRun, utt: Utterance) -> bool:
        """'<unknown word> hazaar ...': the count of the thousands may be a number spelling we do not know."""
        if run.start == 0 or self.registry.multiplier(run.words[0]) is None:
            return False
        if any(ch in CLAUSE_BREAKS for ch in utt.text[utt.tokens[run.start - 1].end : utt.tokens[run.start].start]):
            return False
        before = utt.tokens[run.start - 1].norm
        reg = self.registry
        return not (
            reg.is_everyday(before)
            or reg.is_common(before)
            or reg.is_glue(before)
            or any(before in reg.cue_words(k) for k in ("PHONE", "PIN", "AMOUNT", "CURRENCY"))
        )

    # ---- a cue with no readable number ---------------------------------------------------------
    def _unreadable_after_cue(self, utt: Utterance, claimed: set[int], found: list[Entity]) -> list[Entity]:
        taken = set(claimed) | {i for e in found for i in range(e.start_tok, e.end_tok)}
        out: list[Entity] = []
        for kind, etype in (("PHONE", EType.PHONE), ("PIN", EType.PIN)):
            for i, token in enumerate(utt.tokens):
                if token.norm not in self.registry.fact_cues(kind) or i in taken:
                    continue
                reach = range(i + 1, self._clause_end(utt, i, self.n["cue_lookahead_tokens"]))
                if any(e.start_tok in reach for e in found if e.etype in (EType.PHONE, EType.PIN, EType.AMOUNT)):
                    continue
                garbled = [j for j in reach if self._is_garbled(utt.tokens[j].raw) and j not in taken]
                if garbled:
                    start, end, why = garbled[0], garbled[-1] + 1, "number after the cue word is unreadable"
                elif all(utt.tokens[j].norm in self.registry.marker_words("cue_filler") for j in reach):
                    start, end, why = i, i + 1, "a number was announced but no digits were heard"
                elif len(pieces := [j for j in reach if self._is_number_word(utt.tokens[j].norm)]) \
                        >= self.n["cue_fragment_min_words"]:
                    start, end, why = pieces[0], pieces[-1] + 1, "only fragments of a number were heard after the cue"
                else:
                    continue
                base = dict(
                    etype=etype,
                    surface=utt.span_text(start, end),
                    start_tok=start,
                    end_tok=end,
                    asr_confidence=utt.min_confidence(start, end),
                )
                out.append(self._flag(utt, base, "", base["surface"], why, []))
                taken.update(range(start, end))
                taken.update(reach)
        return out

    @staticmethod
    def _clause_end(utt: Utterance, i: int, lookahead: int) -> int:
        end = i + 1
        while end < min(len(utt.tokens), i + 1 + lookahead):
            if any(ch in CLAUSE_BREAKS for ch in utt.text[utt.tokens[end - 1].end : utt.tokens[end].start]):
                break
            end += 1
        return end

    def _is_number_word(self, norm: str) -> bool:
        return norm.isdigit() or self.registry.number_value(norm) is not None

    def _is_garbled(self, raw: str) -> bool:
        digits = sum(ch.isdigit() for ch in raw)
        return digits >= self.n["garbled_min_digits"] and any(ch.isalpha() for ch in raw)
