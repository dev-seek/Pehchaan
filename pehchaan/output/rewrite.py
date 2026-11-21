"""Write the corrected transcript: replace each resolved span with its display form; flagged spans stay as heard."""
from __future__ import annotations

from ..languages import LanguageRegistry
from ..models import Entity, EType, Status, Utterance


def rewrite(utt: Utterance, entities: list[Entity], registry: LanguageRegistry) -> str:
    currency_words = registry.cue_words("CURRENCY")
    out, pos = [], 0
    for e in sorted(entities, key=lambda x: utt.tokens[x.start_tok].start):
        a, b = utt.tokens[e.start_tok].start, utt.tokens[e.end_tok - 1].end
        if a < pos:
            continue                                   # overlapping spans: first one wins
        display = utt.text[a:b] if e.status == Status.FLAGGED else e.display
        next_tok = utt.tokens[e.end_tok] if e.end_tok < len(utt.tokens) else None
        if e.etype == EType.AMOUNT and next_tok is not None and next_tok.norm in currency_words:
            display = display.lstrip("₹")              # avoid "₹14,500 rupaye"
        out += [utt.text[pos:a], display]
        pos = b
    out.append(utt.text[pos:])
    return "".join(out)
