"""
Turn company records into the six context fields the frozen engine understands.

Records are EVIDENCE, not truth. They can confirm a fact or raise a question. The engine's gate still decides everything, and
money, PINs and phone numbers are never rewritten. Before a record counts as evidence this file drops anything that is
malformed, old, ambiguous, disputed between sources, or simply too much (big lists cause false fixes).

    people    -> contacts[].name
    phones    -> contacts[].number
    places    -> places[]
    amounts   -> a message body "Rs 14,500"    (the only way the engine learns an amount)
    pins      -> a message body "pin 560007"   (the only way the engine learns a PIN)
    companies -> a message from that brand's sender ID, so only brands in the lexicon can be used
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from pehchaan.config import settings
from pehchaan.context.lexicon import brand_by_name
from pehchaan.numbers import rules

from .clean import AMOUNT_IN_TEXT, PIN_IN_TEXT, clean_amount, clean_name, clean_phone, clean_pin, fact_key
from .records import Dropped, Knowledge, KnowledgeReport, SourceReport

_NUMBER_KINDS = {"phones": ("PHONE", clean_phone), "amounts": ("AMOUNT", clean_amount), "pins": ("PIN", clean_pin)}
_NAME_KINDS = {"people": "PERSON", "places": "PLACE", "companies": "ORG"}


@dataclass
class Answer:
    """One source's reply to the hub."""

    name: str
    status: str
    ms: float = 0
    records: list[Knowledge] = field(default_factory=list)
    private: bool = False


@dataclass
class Compiled:
    """The merged context, plus the record of where every fact came from."""

    context: dict
    shareable: dict  # the same, without anything from private sources: what may leave this machine
    report: KnowledgeReport
    backers: dict[tuple[str, str], list[str]]
    own: set[tuple[str, str]]
    has_private: bool = False

    @property
    def used(self) -> bool:
        return bool(self.backers)

    def backed_by(self, kind: str, values: list[str]) -> list[str]:
        """Which sources back any of these values. Empty when the call's own data already knew it."""
        keys = [(kind, fact_key(kind, v)) for v in values if v]
        if any(k in self.own for k in keys):
            return []
        return list(dict.fromkeys(name for k in keys for name in self.backers.get(k, [])))


def _pairs(value: list | dict) -> list[tuple[str | None, object]]:
    if isinstance(value, dict):
        return [(str(label).lower(), item) for label, item in value.items()]
    return [(None, item) for item in value or []]


def _is_stale(record: Knowledge, today: date, max_age_days: int) -> bool:
    if not record.as_of:
        return False
    try:
        return date.fromisoformat(str(record.as_of)[:10]) < today - timedelta(days=max_age_days)
    except ValueError:
        return True  # a date we cannot read cannot prove the record is fresh


class _Merge:
    """Collects what every source said, drops what cannot count, and remembers who backs each fact."""

    def __init__(self, today: date):
        self.cfg, self.today = settings()["knowledge"], today
        self.names: dict[str, list[tuple[str, str, bool]]] = {kind: [] for kind in _NAME_KINDS}
        self.numbers: list[dict] = []
        self.city: str | None = None
        self.city_private = False
        self.city_source: str | None = None
        self.reports: dict[str, SourceReport] = {}
        self.backers: dict[tuple[str, str], list[str]] = {}
        self.contacts: list[dict] = []
        self.places: list[str] = []
        self.messages: list[dict] = []
        self.hidden_people: set[str] = set()
        self.hidden_places: set[str] = set()
        self.hidden_messages: list[dict] = []
        self.hidden_contacts: list[dict] = []

    def drop(self, source: str, kind: str, value, reason: str) -> None:
        self.reports[source].dropped.append(Dropped(kind=kind, value=str(value)[:60], reason=reason))

    def count(self, source: str, kind: str) -> None:
        used = self.reports[source].used
        used[kind] = used.get(kind, 0) + 1

    def back(self, etype: str, value: str, source: str) -> bool:
        """Record a backer. True when this is the first source to hold the fact."""
        key = (etype, fact_key(etype, value))
        first = key not in self.backers
        names = self.backers.setdefault(key, [])
        if source not in names:
            names.append(source)
        return first

    def read(self, answer: Answer) -> None:
        ambiguous = len(answer.records) > 1
        for record in answer.records:
            stale = _is_stale(record, self.today, self.cfg["max_age_days"])
            if record.city and not stale and not self.city:
                self.city, self.city_private, self.city_source = record.city, answer.private, answer.name
            self._read_names(answer, record, stale)
            self._read_numbers(answer, record, stale, ambiguous)

    def _read_names(self, answer: Answer, record: Knowledge, stale: bool) -> None:
        for kind in _NAME_KINDS:
            for item in getattr(record, kind):
                name = clean_name(item, self.cfg["max_value_chars"])
                if name is None:
                    self.drop(answer.name, kind, item, "not a usable name")
                elif stale and kind == "places":
                    self.drop(answer.name, kind, name, "the record is too old")
                else:
                    self.names[kind].append((name, answer.name, answer.private))

    def _read_numbers(self, answer: Answer, record: Knowledge, stale: bool, ambiguous: bool) -> None:
        for kind, (etype, clean) in _NUMBER_KINDS.items():
            for label, item in _pairs(getattr(record, kind)):
                value = clean(item)
                if value is None:
                    self.drop(answer.name, kind, item, "not a valid value")
                elif stale:
                    self.drop(answer.name, kind, value, "the record is too old")
                elif ambiguous:
                    self.drop(answer.name, kind, value, "several records match this caller")
                else:
                    self.numbers.append(
                        {"kind": kind, "etype": etype, "label": label, "value": value, "source": answer.name,
                         "private": answer.private}
                    )

    def settle_conflicts(self) -> list[str]:
        """Two sources giving one labelled number different values: neither counts, because we cannot tell who is right."""
        labelled: dict[tuple[str, str], set[str]] = {}
        for n in self.numbers:
            if n["label"]:
                labelled.setdefault((n["kind"], n["label"]), set()).add(n["value"])
        disputed = {key for key, values in labelled.items() if len(values) > 1}
        conflicts = [f"{key[1]}: " + " vs ".join(sorted(labelled[key])) for key in disputed]
        for n in self.numbers:
            if (n["kind"], n["label"]) in disputed:
                self.drop(n["source"], n["kind"], n["value"], "another source gives a different value")
        self.numbers = [n for n in self.numbers if (n["kind"], n["label"]) not in disputed]
        return sorted(conflicts)

    def add_names(self) -> None:
        limits = {
            "people": self.cfg["max_names"],
            "places": self.cfg["max_places"],
            "companies": self.cfg["max_places"],
        }
        for kind, entries in self.names.items():
            etype, added = _NAME_KINDS[kind], 0
            secret = {fact_key(etype, n) for n, _, private in entries if private}
            for name, source, _ in entries:
                brand = brand_by_name(name) if kind == "companies" else None
                if kind == "companies" and (brand is None or not brand.sender_ids):
                    self.drop(source, kind, name, "not a brand the engine knows")
                    continue
                value = brand.name if brand else name
                is_secret = fact_key(etype, name) in secret or fact_key(etype, value) in secret
                if (etype, fact_key(etype, value)) not in self.backers and added >= limits[kind]:
                    self.drop(source, kind, value, "over the limit for one call")
                    continue
                self.count(source, kind)
                if not self.back(etype, value, source):
                    continue
                added += 1
                if kind == "people":
                    self.contacts.append({"name": value})
                    if is_secret:
                        self.hidden_people.add(value)
                elif kind == "places":
                    self.places.append(value)
                    if is_secret:
                        self.hidden_places.add(value)
                else:
                    message = {"sender": brand.sender_ids[0], "body": ""}
                    self.messages.append(message)
                    if is_secret:
                        self.hidden_messages.append(message)

    def add_numbers(self) -> None:
        added = 0
        secret = {(n["etype"], fact_key(n["etype"], n["value"])) for n in self.numbers if n["private"]}
        for n in self.numbers:
            key = (n["etype"], fact_key(n["etype"], n["value"]))
            if key not in self.backers and added >= self.cfg["max_numbers"]:
                self.drop(n["source"], n["kind"], n["value"], "over the limit for one call")
                continue
            self.count(n["source"], n["kind"])
            if not self.back(n["etype"], n["value"], n["source"]):
                continue
            added += 1
            if n["etype"] == "PHONE":
                entry = {"number": n["value"]}
                self.contacts.append(entry)
                hidden = self.hidden_contacts
            else:
                body = f"pin {n['value']}" if n["etype"] == "PIN" else f"Rs {rules.format_inr(float(n['value']), symbol=False)}"
                entry = {"sender": "", "body": body}
                self.messages.append(entry)
                hidden = self.hidden_messages
            if key in secret:
                hidden.append(entry)


def _own_facts(base: dict) -> set[tuple[str, str]]:
    """What the call's own data already held, so a company system is not credited for it."""
    own = {("PERSON", fact_key("PERSON", c["name"])) for c in base.get("contacts") or [] if c.get("name")}
    own |= {("PHONE", fact_key("PHONE", c["number"])) for c in base.get("contacts") or [] if c.get("number")}
    own |= {("PLACE", fact_key("PLACE", p)) for p in base.get("places") or []}
    number = (base.get("caller") or {}).get("number")
    if number:
        own.add(("PHONE", fact_key("PHONE", number)))
    for message in base.get("sms") or []:
        body = message.get("body", "")
        own |= {("AMOUNT", fact_key("AMOUNT", m)) for m in AMOUNT_IN_TEXT.findall(body)}
        if "pin" in body.lower():
            own |= {("PIN", m) for m in PIN_IN_TEXT.findall(body)}
    return own


def compile_knowledge(base: dict, answers: list[Answer], ms: float = 0, today: date | None = None) -> Compiled:
    """Merge every answer into `base`. Anything from `base` (the call's own data) is left exactly as it was."""
    merge = _Merge(today or date.today())
    for answer in answers:
        merge.reports[answer.name] = SourceReport(
            name=answer.name, status=answer.status, ms=answer.ms, private=answer.private
        )
        merge.read(answer)
    conflicts = merge.settle_conflicts()
    merge.add_names()
    merge.add_numbers()

    contacts, places, sms = base.get("contacts") or [], base.get("places") or [], base.get("sms") or []
    context = {
        **base,
        "contacts": [*contacts, *merge.contacts],
        "places": [*places, *merge.places],
        "sms": [*sms, *merge.messages],
    }
    shareable = {
        **base,
        "contacts": [
            *contacts,
            *(
                c
                for c in merge.contacts
                if c.get("name") not in merge.hidden_people and not any(c is h for h in merge.hidden_contacts)
            ),
        ],
        "places": [*places, *(p for p in merge.places if p not in merge.hidden_places)],
        "sms": [*sms, *(m for m in merge.messages if not any(m is h for h in merge.hidden_messages))],
    }
    if merge.city and not (base.get("user") or {}).get("city"):
        context["user"] = {**(base.get("user") or {}), "city": merge.city}
        merge.count(merge.city_source, "city")
        if not merge.city_private:
            shareable["user"] = context["user"]
    report = KnowledgeReport(sources=[merge.reports[a.name] for a in answers], conflicts=conflicts, ms=round(ms, 1))
    has_private = any(a.private and merge.reports[a.name].used for a in answers)
    return Compiled(context, shareable, report, merge.backers, _own_facts(base), has_private)
