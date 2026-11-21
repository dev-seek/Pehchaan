"""Write the corrected transcript: replace each resolved span with its display form; flagged spans stay as heard."""

from __future__ import annotations

from ..languages import LanguageRegistry
from ..models import Entity, EType, Status, Utterance


def rewrite(utt: Utterance, entities: list[Entity], registry: LanguageRegistry) -> str:
    return rewrite_with_spans(utt, entities, registry)[0]


def rewrite_with_spans(utt: Utterance, entities: list[Entity], registry: LanguageRegistry) -> tuple[str, dict]:
    """Return rewritten text and output character offsets by entity index."""
    currency_words = registry.cue_words("CURRENCY")
    out, spans, pos, output_pos = [], {}, 0, 0
    for i, e in sorted(enumerate(entities), key=lambda entry: utt.tokens[entry[1].start_tok].start):
        a, b = utt.tokens[e.start_tok].start, utt.tokens[e.end_tok - 1].end
        if a < pos:
            continue  # overlapping spans: first one wins
        display = utt.text[a:b] if e.status == Status.FLAGGED else e.display
        next_tok = utt.tokens[e.end_tok] if e.end_tok < len(utt.tokens) else None
        if e.etype == EType.AMOUNT and next_tok is not None and next_tok.norm in currency_words:
            display = display.lstrip("₹")  # avoid "₹14,500 rupaye"
        start = output_pos + a - pos
        output_pos = start + len(display)
        spans[i] = {"start": start, "end": output_pos, "input_start": a, "input_end": b}
        out += [utt.text[pos:a], display]
        pos = b
    out.append(utt.text[pos:])
    return "".join(out), spans
