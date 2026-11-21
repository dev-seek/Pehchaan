"""Build an Utterance from a transcript: tokens, per-token ASR confidence, language tags and profile."""
from __future__ import annotations

from .asr import token_confidences
from .languages import LanguageRegistry, annotate
from .models import Utterance
from .text import tokenize


def build_utterance(text: str, registry: LanguageRegistry, asr_pieces: list[dict] | None = None) -> Utterance:
    tokens = tokenize(text)
    confidences = token_confidences([(t.start, t.end) for t in tokens], asr_pieces or [], text)
    profile = annotate(tokens, registry)
    return Utterance(text=text, tokens=tokens, confidences=confidences, language=profile)
