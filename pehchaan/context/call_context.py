"""
CallContext: everything the phone already knows when a call comes in, turned into candidates and known numbers.

Input (a plain dict, e.g. from the app or the benchmark):
    {"user": {"id": "u1", "city": "Hyderabad"},
     "caller": {"number": "9848012345", "cnap_name": "HDFC BANK"},
     "contacts": [{"name": "Venkateswara Rao", "number": "9848012345"}],
     "sms": [{"sender": "VM-HDFCBK", "body": "EMI of Rs 14,500 due on 25-Nov"}],
     "places": ["Kondapur"], "domain": "bank EMI reminder"}

Context LEVELS (the benchmark's ablation ladder, inspired by IndicContextEval's graded prompting):
    C0 nothing (rules only) · C1 domain line only · C2 global lists (brands + city localities)
    C3 C2 + THIS call's context  <- the product setting
    C4 = C3 machinery fed an adversarial dict (true entities removed, sound-alike decoys added) by the benchmark
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import Candidate, EType
from ..numbers import rules
from ..text import normalize
from . import lexicon

LEVELS = ("C0", "C1", "C2", "C3", "C4")
_AMOUNT_IN_SMS = re.compile(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)", re.I)
_PHONE_IN_SMS = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})(?!\d)")
_PIN_IN_SMS = re.compile(r"(?<!\d)([1-9]\d{5})(?!\d)")


@dataclass
class CallContext:
    level: str = "C3"
    user_id: str | None = None
    city: str | None = None
    domain: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    phones: set[str] = field(default_factory=set)
    amounts: set[float] = field(default_factory=set)
    pins: set[str] = field(default_factory=set)

    @classmethod
    def build(cls, raw: dict | None, level: str = "C3") -> CallContext:
        if level not in LEVELS:
            raise ValueError(f"unknown context level {level!r}; use one of {LEVELS}")
        raw = raw or {}
        user = raw.get("user") or {}
        ctx = cls(level=level, user_id=user.get("id"))
        if level != "C0":
            ctx.domain = raw.get("domain")
        if level in ("C2", "C3", "C4"):
            ctx.city = user.get("city")
            ctx._add_global_lists()
        if level in ("C3", "C4"):
            ctx._add_this_call(raw)
        ctx._dedupe()
        return ctx

    # ---- builders ------------------------------------------------------------------------------
    def _add_global_lists(self) -> None:
        shorts = lexicon.short_names()
        for b in lexicon.brands():
            self.candidates.append(Candidate(b.name, EType.ORG, "lexicon:brands", per_call=False))
            for alias in b.aliases + shorts.get(b.name, ()):
                self.candidates.append(Candidate(alias, EType.ORG, "lexicon:brands", per_call=False, canonical=b.name))
        for place in lexicon.localities(self.city):
            self.candidates.append(Candidate(place, EType.PLACE, "lexicon:localities", per_call=False))

    def _add_this_call(self, raw: dict) -> None:
        caller = raw.get("caller") or {}
        self._add_phone(caller.get("number"))
        if caller.get("cnap_name"):
            brand = lexicon.brand_by_name(caller["cnap_name"])
            if brand:
                self.candidates.append(Candidate(brand.name, EType.ORG, "caller_id", per_call=True))
            else:
                self.candidates.append(Candidate(caller["cnap_name"].title(), EType.PERSON, "caller_id", per_call=True))
        for c in raw.get("contacts") or []:
            if c.get("name"):
                self.candidates.append(Candidate(c["name"], EType.PERSON, "contacts", per_call=True))
            self._add_phone(c.get("number"))
        for sms in raw.get("sms") or []:
            brand = lexicon.brand_for_sender(sms.get("sender", ""))
            if brand:
                self.candidates.append(Candidate(brand.name, EType.ORG, "sms", per_call=True))
            self._read_sms_body(sms.get("body", ""))
        for place in raw.get("places") or []:
            self.candidates.append(Candidate(place, EType.PLACE, "saved_places", per_call=True))

    def _add_phone(self, number: str | None) -> None:
        if number:
            d = rules.strip_phone_prefix(re.sub(r"\D", "", number))
            if rules.is_mobile(d):
                self.phones.add(d)

    def _read_sms_body(self, body: str) -> None:
        for m in _AMOUNT_IN_SMS.finditer(body):
            try:
                self.amounts.add(float(m.group(1).replace(",", "")))
            except ValueError:
                continue
        for m in _PHONE_IN_SMS.finditer(body):
            self.phones.add(re.sub(r"\D", "", m.group(1)))
        if "pin" in body.lower():
            self.pins.update(m.group(1) for m in _PIN_IN_SMS.finditer(body))

    def _dedupe(self) -> None:
        best: dict[tuple, Candidate] = {}
        for c in self.candidates:
            k = (normalize(c.text), c.etype)
            if k not in best or (c.per_call and not best[k].per_call):
                best[k] = c
        self.candidates = list(best.values())

    # ---- views ---------------------------------------------------------------------------------
    def keyword_list(self, max_n: int) -> list[str]:
        """Keywords for ASR biasing (baseline B1): this call's entities first, then global lists."""
        ordered = [c.text for c in self.candidates if c.per_call] + [c.text for c in self.candidates if not c.per_call]
        return list(dict.fromkeys(ordered))[:max_n]
