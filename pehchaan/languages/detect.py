"""
Language routing for one utterance.

Each token gets a language tag:
  * Indic script  -> the pack that owns that script (Devanagari -> hi, Telugu -> te; vocabulary breaks ties)
  * spelled acronym in Indic script (एचडीएफसी) -> decoded to Latin letters ("hdfc"), tagged en
  * Latin word    -> the pack(s) whose vocabulary contains it (hai/raha -> hi, sir/number -> en); unknown -> None
  * digits        -> None
The utterance profile = share of tagged tokens per language. The dominant language decides which language
the clarifying question is asked in. Every other layer uses the merged registry, so mixing is never a problem.
"""
from __future__ import annotations

from collections import Counter

from ..models import LanguageProfile, Token
from .registry import LanguageRegistry


def annotate(tokens: list[Token], registry: LanguageRegistry) -> LanguageProfile:
    """Tag tokens in place (and decode Indic-script acronyms); return the utterance language profile."""
    scripts: Counter[str] = Counter()
    langs: Counter[str] = Counter()
    for t in tokens:
        scripts[t.script] += 1
        if t.norm.isdigit():
            t.lang = None
            continue
        if t.script != "latin":
            acronym = registry.decode_spelled_acronym(t.norm) if t.norm.isalpha() else None
            if acronym:
                t.norm, t.lang = acronym, "en"
            else:
                t.lang = registry.language_for_script(t.script, t.norm)
        else:
            owners = registry.languages_of_word(t.norm)
            t.lang = next(iter(owners)) if len(owners) == 1 else None   # shared or unknown word: no vote
        if t.lang:
            langs[t.lang] += 1
    total = sum(langs.values())
    shares = {c: n / total for c, n in langs.items()} if total else {}
    if shares:
        best = max(shares.values())
        dominant = next(c for c in registry.order if shares.get(c) == best)
    else:
        dominant = registry.default
    return LanguageProfile(shares=shares, dominant=dominant, scripts=dict(scripts))
