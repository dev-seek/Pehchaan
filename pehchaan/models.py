"""
Data types shared across the engine. No logic lives here, only shapes.

Reading guide: a transcript becomes an `Utterance` (tokens + confidences + language profile); resolvers turn
spans of it into `Entity` objects, each with a `Status` and a human-readable reason.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class EType(str, Enum):
    """Kinds of facts we take responsibility for."""
    PERSON = "PERSON"
    ORG = "ORG"
    PLACE = "PLACE"
    PHONE = "PHONE"
    PIN = "PIN"
    AMOUNT = "AMOUNT"


class Status(str, Enum):
    """What we did with a fact."""
    FIXED = "FIXED"           # changed it, with a reason
    CONFIRMED = "CONFIRMED"   # independent evidence (context / rules) agrees with what the ASR heard
    KEPT = "KEPT"             # well-formed, no evidence either way: left as heard
    FLAGGED = "FLAGGED"       # could not resolve: ask the caller one short question


@dataclass
class Token:
    raw: str                  # the word exactly as in the input text (edge punctuation excluded)
    norm: str                 # normalised Latin form used for all comparisons
    start: int                # character offsets in the input text
    end: int
    script: str = "latin"     # devanagari | telugu | ... | latin
    lang: str | None = None   # language code assigned by languages.detect (None = unknown / digits)


@dataclass
class LanguageProfile:
    """Which languages an utterance mixes, e.g. {'hi': 0.62, 'en': 0.38} for typical Hinglish."""
    shares: dict[str, float]
    dominant: str
    scripts: dict[str, int]

    @property
    def label(self) -> str:
        top = sorted(self.shares.items(), key=lambda kv: -kv[1])
        if len(top) >= 2 and top[1][1] >= 0.2:
            return f"code-mixed {top[0][0]}+{top[1][0]}"
        return self.dominant


@dataclass
class Utterance:
    """One transcript, prepared for the resolvers."""
    text: str
    tokens: list[Token]
    confidences: list[float | None]   # per token: min logprob of the ASR pieces covering it
    language: LanguageProfile

    def span_text(self, start: int, end: int) -> str:
        return self.text[self.tokens[start].start:self.tokens[end - 1].end]

    def min_confidence(self, start: int, end: int) -> float | None:
        vals = [c for c in self.confidences[start:end] if c is not None]
        return min(vals) if vals else None


@dataclass
class Candidate:
    """Something the phone already knows that a heard span might refer to."""
    text: str                 # how it is written, e.g. "Venkateswara Rao" or an alias "HDFC"
    etype: EType
    source: str               # contacts | caller_id | sms | saved_places | memory | lexicon:brands | ...
    per_call: bool            # True = from THIS call's context (trusted, small list)
    canonical: str | None = None   # for aliases: the official name to output ("HDFC" -> "HDFC Bank")

    @property
    def output(self) -> str:
        return self.canonical or self.text


@dataclass
class Entity:
    etype: EType
    surface: str              # what the ASR wrote (substring of the input text)
    start_tok: int
    end_tok: int
    value: str                # final value: canonical text, digits, or amount
    display: str              # how it is written in the output transcript
    status: Status
    source: str               # rule | context | lexicon | memory | llm
    reason: str               # plain-English explanation, shown in the UI
    distance: float | None = None
    asr_confidence: float | None = None
    candidates: list[dict] = field(default_factory=list)
    clarifier: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["etype"] = self.etype.value
        d["status"] = self.status.value
        return d
