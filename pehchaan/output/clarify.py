"""One short clarifying question per unresolved fact, in the caller's dominant language (templates from the packs)."""
from __future__ import annotations

from ..languages import LanguageRegistry

FALLBACK_QUESTION = "Could you repeat that?"


def question(registry: LanguageRegistry, lang: str, etype: str, options: list[str], heard: str) -> str:
    arity = "two" if len(options) >= 2 else ("one" if options else "none")
    template = registry.clarify_template(lang, etype, arity)
    if template is None and arity == "two":
        template = registry.clarify_template(lang, etype, "one")
    if template is None:
        return FALLBACK_QUESTION
    return template.format(a=options[0] if options else heard, b=options[1] if len(options) > 1 else "", heard=heard)
