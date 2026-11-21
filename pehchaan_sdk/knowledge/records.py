"""
What a knowledge source receives and returns. No logic beyond reading the shapes.

A source is asked about one call (`CallKey`) and answers with what the company knows about that customer (`Knowledge`).
Numbers may carry a label, for example {"emi": 14500}. Two sources that give the same label different values disagree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields

from pydantic import BaseModel, Field

LISTS = ("people", "companies", "places")
NUMBERS = ("phones", "amounts", "pins")


def _as_list(value, kind: str) -> list:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return list(value)
    if isinstance(value, str | int | float):
        return [value]
    raise TypeError(f"{kind} must be a value or a list of values")


@dataclass(frozen=True)
class CallKey:
    """The only things a source is told about a call. It never receives the audio or the transcript."""

    phone: str | None = None
    customer_id: str | None = None
    city: str | None = None
    domain: str | None = None

    @property
    def usable(self) -> bool:
        return bool(self.phone or self.customer_id)

    @property
    def cache_key(self) -> tuple:
        return (self.phone, self.customer_id, self.city, self.domain)

    @classmethod
    def from_context(cls, raw: dict) -> CallKey:
        user = raw.get("user") or {}
        digits = re.sub(r"\D", "", str((raw.get("caller") or {}).get("number") or ""))
        return cls(
            phone=digits[-10:] if len(digits) >= 10 else None,
            customer_id=raw.get("customer_id") or user.get("id"),
            city=user.get("city"),
            domain=raw.get("domain"),
        )


@dataclass
class Knowledge:
    """One customer's record from one company system. Every field is optional."""

    people: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    phones: list | dict = field(default_factory=list)
    amounts: list | dict = field(default_factory=list)
    pins: list | dict = field(default_factory=list)
    city: str | None = None
    as_of: str | None = None  # ISO date of the record. Old money, PINs and places stop counting as evidence

    def __post_init__(self) -> None:
        """Company data is messy: accept one value where a list belongs, and refuse a shape we cannot read."""
        for kind in LISTS:
            setattr(self, kind, _as_list(getattr(self, kind), kind))
        for kind in NUMBERS:
            value = getattr(self, kind)
            if not isinstance(value, dict):
                setattr(self, kind, _as_list(value, kind))

    @classmethod
    def of(cls, value: Knowledge | dict) -> Knowledge:
        if isinstance(value, Knowledge):
            return value
        if not isinstance(value, dict):
            raise TypeError("a knowledge source must return Knowledge, a dict, a list of them, or None")
        known = {f.name for f in fields(cls)}
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"unknown knowledge fields: {sorted(unknown)}")
        return cls(**value)


class Dropped(BaseModel):
    kind: str
    value: str
    reason: str


class SourceReport(BaseModel):
    """What one source did for this call."""

    name: str
    status: str = Field(description="ok, no_record, timeout, error or skipped")
    ms: float = 0
    used: dict[str, int] = Field(default_factory=dict, description="How many facts of each kind became evidence")
    dropped: list[Dropped] = Field(default_factory=list, description="What was refused as evidence, and why")
    private: bool = Field(default=False, description="Its names were kept away from the speech model and the LLM judge")


class KnowledgeReport(BaseModel):
    """Which company systems were consulted for this call and what they contributed."""

    sources: list[SourceReport]
    conflicts: list[str] = Field(default_factory=list, description="Facts two sources disagreed on, so neither counted")
    ms: float = 0
