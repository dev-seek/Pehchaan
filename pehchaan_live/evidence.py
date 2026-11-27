"""Locate caller evidence and distinguish candidate values from authorization."""

import re
from functools import lru_cache

from .contracts import FieldDecision, Span, Turn
from .policy import FieldRule, Policy
from .values import canonical

CLAUSE = re.compile(r"[^;\n.!?]+(?:\.(?=[0-9])[0-9]+[^;\n.!?]*)*")
# An entire clause must read as a single value. The cue cannot start inside quoted or hypothetical text.
CUE_GAP = r"(?:\s*[:=]\s*|\s+is\s+|\s+)"
INVALID_REPLY = re.compile(r"^(?:yes|no|okay|ok|sure|correct|haan|nahi|yeah|yep|unknown|unclear)$", re.I)


@lru_cache(maxsize=512)
def _cue_pattern(cues: tuple[str, ...]) -> re.Pattern:
    alternatives = "|".join(re.escape(cue) for cue in sorted(cues, key=len, reverse=True))
    return re.compile(rf"^(?:{alternatives}){CUE_GAP}(?P<value>.+)$", re.IGNORECASE)


@lru_cache(maxsize=32)
def _boundary(cues: tuple[str, ...]) -> re.Pattern:
    alternatives = "|".join(re.escape(cue) for cue in sorted(cues, key=len, reverse=True))
    return re.compile(rf"(?:,\s*(?:and\s+)?|\s+and\s+)(?=(?:{alternatives}){CUE_GAP})", re.IGNORECASE)


def _clauses(text: str, policy: Policy):
    boundary = _boundary(tuple(cue for field in policy.fields.values() for cue in field.cues))
    for match in CLAUSE.finditer(text):
        offset = match.start()
        for split in boundary.finditer(match[0]):
            yield text[offset:match.start() + split.start()], offset
            offset = match.start() + split.end()
        yield text[offset:match.end()], offset


@lru_cache(maxsize=32)
def _defer_pattern(phrases: tuple[str, ...]) -> re.Pattern:
    alternatives = "|".join(re.escape(phrase) for phrase in phrases)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def unsafe_statement(text: str, policy: Policy) -> bool:
    return "?" in text or bool(policy.defer_phrases and _defer_pattern(tuple(policy.defer_phrases)).search(text))


def _matches(turn_id: str, source: str, text: str, rule: FieldRule, policy: Policy) -> list[tuple[str | None, Span]]:
    pattern = _cue_pattern(tuple(rule.cues))
    matches = []
    for clause, offset in _clauses(text, policy):
        trimmed = clause.lstrip()
        match = pattern.fullmatch(trimmed)
        if match:
            raw = match["value"].rstrip()
            start = offset + (len(clause) - len(trimmed)) + match.start("value")
            if raw:
                span = Span(turn_id=turn_id, source=source, start=start, end=start + len(raw), text=raw)
                matches.append((canonical(raw, rule, is_spoken=True), span))
    return matches


def _one_value(matches: list[tuple[str | None, Span]]) -> str | None:
    values = {value for value, _ in matches}
    return next(iter(values)) if len(values) == 1 else None


def unresolved(name: str, reason: str, spans: list[Span] | None = None) -> FieldDecision:
    return FieldDecision(field=name, status="unresolved", reason=reason, spans=spans or [])


def _needs_confidence(turn: Turn, policy: Policy) -> bool:
    if not policy.calibration.confidence_floors:
        return False
    provider = turn.provider
    scope = f"{provider.name}/{provider.model}/{provider.version}" if provider and provider.version else ""
    floor = policy.calibration.confidence_floors.get(scope)
    # A score from another provider or model version is not comparable.
    return floor is None or turn.confidence is None or turn.confidence < floor


def evaluate(turn: Turn, name: str, policy: Policy) -> FieldDecision:
    rule = policy.fields[name]
    if not rule.supported:
        return FieldDecision(field=name, status="unsupported", reason="validator_unavailable")
    if turn.status != "finalized" or unsafe_statement(turn.transcript, policy):
        return unresolved(name, "interrupted_or_ambiguous_turn")
    primary = _matches(turn.turn_id, "transcript", turn.transcript, rule, policy)
    spans = [span for _, span in primary]
    value = _one_value(primary)
    if value is None:
        return unresolved(name, "ambiguous_or_invalid_value" if spans else "missing_evidence", spans)
    if rule.evidence == "readback":
        return unresolved(name, "caller_readback_required", spans)
    if _needs_confidence(turn, policy):
        return unresolved(name, "insufficient_scoped_confidence", spans)
    if rule.evidence == "agreement" or name in policy.calibration.agreement_for:
        alternative = turn.alternative or ""
        other = _matches(turn.turn_id, "alternative", alternative, rule, policy)
        spans.extend(span for _, span in other)
        if (
            not turn.provider
            or not turn.alternative_provider
            or not turn.alternative_context_free
            or unsafe_statement(alternative, policy)
            or _one_value(other) != value
        ):
            return unresolved(name, "independent_agreement_missing", spans)
        reason = "transcripts_agree"
    else:
        reason = "caller_span_matches"
    return FieldDecision(field=name, status="supported", value=value, reason=reason, spans=spans)


def readback(turn: Turn, name: str, policy: Policy) -> FieldDecision:
    raw = turn.transcript.strip().removesuffix(".").rstrip()
    if (
        turn.status != "finalized"
        or not raw
        or INVALID_REPLY.fullmatch(raw)
        or unsafe_statement(turn.transcript, policy)
        or ";" in raw
        or "\n" in raw
    ):
        return unresolved(name, "readback_interrupted_or_ambiguous")
    rule = policy.fields[name]
    start = len(turn.transcript) - len(turn.transcript.lstrip())
    match = _cue_pattern(tuple(rule.cues)).fullmatch(raw)
    if match:
        start += match.start("value")
        raw = match["value"].rstrip()
    value = canonical(raw, rule, is_spoken=True)
    if value is None or INVALID_REPLY.fullmatch(raw):
        return unresolved(name, "readback_interrupted_or_ambiguous")
    span = Span(turn_id=turn.turn_id, source="readback", start=start, end=start + len(raw), text=raw)
    return FieldDecision(field=name, status="supported", value=value, reason="caller_readback", spans=[span])
