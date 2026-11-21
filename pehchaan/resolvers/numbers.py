"""
NumberResolver: phone numbers, PIN codes and amounts.

Steps per number run:
 1. decide its KIND from validity and nearby cue words ("number", "pin", "rupaye", "EMI") in any active language
 2. apply that kind's rule: confirm against context, repair known ASR mistakes, or flag
Policy (DECISIONS D-007): money and phone numbers are never changed silently unless the ASR itself was unsure.
"""
from __future__ import annotations

from collections.abc import Callable

from ..config import settings
from ..context import CallContext, lexicon
from ..languages import LanguageRegistry
from ..models import Entity, EType, Status, Utterance
from ..numbers import NumberRun, find_runs, rules
from ..output import question

CUE_WINDOW_BEFORE, CUE_WINDOW_AFTER = 5, 3


class NumberResolver:
    name = "numbers"

    def __init__(self, registry: LanguageRegistry):
        self.registry = registry
        self.cfg = settings()
        self._rules: dict[EType, Callable[..., Entity | None]] = {
            EType.PHONE: self._phone, EType.PIN: self._pin, EType.AMOUNT: self._amount}

    def resolve(self, utt: Utterance, ctx: CallContext, claimed: set[int]) -> list[Entity]:
        out = []
        for run in find_runs(utt.tokens, self.registry):
            if any(i in claimed for i in range(run.start, run.end)):
                continue
            etype = self._kind_of(run, utt)
            if etype is None:
                continue                      # "5 baje", "2 din": not a fact we take responsibility for
            base = dict(etype=etype, surface=utt.span_text(run.start, run.end), start_tok=run.start,
                        end_tok=run.end, asr_confidence=utt.min_confidence(run.start, run.end))
            entity = self._rules[etype](run, ctx, utt.language.dominant, base)
            if entity:
                out.append(entity)
        return out

    # ---- kind ----------------------------------------------------------------------------------
    def _cue_distance(self, utt: Utterance, run: NumberRun, kind: str) -> int | None:
        words = self.registry.cue_words(kind)
        best = None
        for i in range(max(0, run.start - CUE_WINDOW_BEFORE), min(len(utt.tokens), run.end + CUE_WINDOW_AFTER)):
            if not (run.start <= i < run.end) and utt.tokens[i].norm in words:
                d = run.start - i if i < run.start else i - (run.end - 1)
                best = d if best is None else min(best, d)
        return best

    def _kind_of(self, run: NumberRun, utt: Utterance) -> EType | None:
        cue = {k: self._cue_distance(utt, run, k) for k in ("PHONE", "PIN", "AMOUNT")}
        digits = rules.strip_phone_prefix(run.digit_reading)
        amount_closer = cue["AMOUNT"] is not None and (cue["PHONE"] is None or cue["AMOUNT"] <= cue["PHONE"])
        if rules.is_mobile(digits) and not (run.has_multiplier and amount_closer):
            return EType.PHONE
        if cue["PIN"] is not None and 5 <= len(run.digit_reading) <= 7 and not run.has_multiplier:
            return EType.PIN
        if cue["AMOUNT"] is not None or run.has_multiplier:
            return EType.AMOUNT
        if cue["PHONE"] is not None and 8 <= len(digits) <= 13:
            return EType.PHONE
        return None

    def _ask(self, lang: str, etype: str, options: list[str], heard: str) -> str:
        return question(self.registry, lang, etype, options, heard)

    def _asr_unsure(self, conf: float | None) -> bool:
        return conf is not None and conf < self.cfg["matching"]["low_conf_logprob"]

    # ---- PHONE -----------------------------------------------------------------------------------
    def _phone(self, run: NumberRun, ctx: CallContext, lang: str, base: dict) -> Entity:
        d = rules.strip_phone_prefix(run.digit_reading)
        conf = base["asr_confidence"]
        max_edits = self.cfg["numbers"]["phone_context_max_digit_edits"]
        near = sorted(p for p in ctx.phones if rules.digit_edit_distance(d, p) <= max_edits and p != d)
        fmt = rules.format_phone
        if rules.is_mobile(d):
            if d in ctx.phones:
                return Entity(value=d, display=fmt(d), status=Status.CONFIRMED, source="context",
                              reason="matches a number already on this phone (caller ID / contacts / SMS)", **base)
            if len(near) == 1 and self._asr_unsure(conf):
                return Entity(value=near[0], display=fmt(near[0]), status=Status.FIXED, source="context",
                              reason=f"one digit from known number {fmt(near[0])} and the ASR was unsure", **base)
            if len(near) == 1 and conf is None:
                return Entity(value=d, display=fmt(d), status=Status.FLAGGED, source="context",
                              reason=f"valid number, but one digit away from known {fmt(near[0])}",
                              candidates=[{"text": fmt(near[0]), "source": "context"}],
                              clarifier=self._ask(lang, "PHONE", [fmt(near[0])], d), **base)
            return Entity(value=d, display=fmt(d), status=Status.KEPT, source="rule",
                          reason="valid Indian mobile number (10 digits, starts 6-9)", **base)
        if len(near) == 1:
            return Entity(value=near[0], display=fmt(near[0]), status=Status.FIXED, source="context",
                          reason=f"heard {len(d)} digits; one edit from known number {fmt(near[0])}", **base)
        stutter = sorted(r for r in rules.stutter_repairs(d) if rules.is_mobile(r)) if len(d) == 11 else []
        if len(stutter) == 1:
            return Entity(value=stutter[0], display=fmt(stutter[0]), status=Status.FIXED, source="rule",
                          reason="11 digits with a doubled digit: removed the stutter to get a valid mobile", **base)
        options = [fmt(x) for x in stutter[:2]]
        return Entity(value=d, display=d, status=Status.FLAGGED, source="rule",
                      reason=f"{len(d)} digits is not a valid Indian mobile number",
                      candidates=[{"text": x, "source": "repair"} for x in options],
                      clarifier=self._ask(lang, "PHONE", options[:1], d), **base)

    # ---- PIN ---------------------------------------------------------------------------------------
    def _pin(self, run: NumberRun, ctx: CallContext, lang: str, base: dict) -> Entity:
        d = run.digit_reading
        prefixes = lexicon.pin_prefixes(ctx.city) if self.cfg["numbers"]["pin_check_city_prefix"] else []

        def valid(p: str) -> bool:
            return rules.is_valid_pin(p, prefixes)

        if valid(d):
            known = d in ctx.pins
            why = "matches a PIN on this phone" if known else (
                f"valid PIN for {ctx.city}" if prefixes else "valid 6-digit PIN")
            return Entity(value=d, display=d, status=Status.CONFIRMED if known else Status.KEPT,
                          source="context" if known else "rule", reason=why, **base)
        stutter = sorted(r for r in rules.stutter_repairs(d) if valid(r)) if len(d) == 7 else []
        deletions = sorted(r for r in rules.single_deletions(d) if valid(r)) if len(d) == 7 else []
        near = sorted(p for p in ctx.pins if rules.digit_edit_distance(d, p) <= 1)
        pick = near if len(near) == 1 else stutter if len(stutter) == 1 else deletions if len(deletions) == 1 else []
        if pick:
            return Entity(value=pick[0], display=pick[0], status=Status.FIXED, source="context" if near else "rule",
                          reason=f"heard '{d}' ({len(d)} digits); the only valid PIN one edit away is {pick[0]}",
                          **base)
        options = (stutter + [r for r in deletions if r not in stutter])[:2]
        why = f"'{d}' is not a valid PIN" + (f" for {ctx.city}" if prefixes else "")
        return Entity(value=d, display=d, status=Status.FLAGGED, source="rule", reason=why,
                      candidates=[{"text": r, "source": "repair"} for r in options],
                      clarifier=self._ask(lang, "PIN", options[:1], d), **base)

    # ---- AMOUNT ------------------------------------------------------------------------------------
    def _amount(self, run: NumberRun, ctx: CallContext, lang: str, base: dict) -> Entity | None:
        v = run.value_reading if run.value_reading is not None else (
            float(run.digit_reading) if run.digit_reading else None)
        if v is None or v <= 0:
            return None
        alternatives = list(run.teen_ty_alternatives)
        if len(run.words) == 1 and run.words[0].isdigit():
            alternatives += [float(x) for x in rules.teen_ty_digit_variants(run.words[0])]
        inr = rules.format_inr
        if v in ctx.amounts:
            return Entity(value=f"{v:g}", display=inr(v), status=Status.CONFIRMED, source="context",
                          reason="matches an amount in this user's SMS", **base)
        hits = [a for a in alternatives if a in ctx.amounts]
        if len(hits) == 1:
            a = hits[0]
            if self._asr_unsure(base["asr_confidence"]):
                return Entity(value=f"{a:g}", display=inr(a), status=Status.FIXED, source="context",
                              reason=f"teen/ty mix-up: heard {inr(v)} (ASR unsure), SMS says {inr(a)}", **base)
            return Entity(value=f"{v:g}", display=inr(v), status=Status.FLAGGED, source="context",
                          reason=f"heard {inr(v)} but SMS says {inr(a)} (classic teen/ty confusion)",
                          candidates=[{"text": inr(v), "source": "asr"}, {"text": inr(a), "source": "context"}],
                          clarifier=self._ask(lang, "AMOUNT", [inr(a)], inr(v)), **base)
        return Entity(value=f"{v:g}", display=inr(v), status=Status.KEPT, source="rule",
                      reason="amount read with Indian number rules (lakh/hazaar/saade...)", **base)
