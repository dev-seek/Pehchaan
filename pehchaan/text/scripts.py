"""Unicode script detection and cleanup of invisible / special characters before transliteration."""
from __future__ import annotations

from indic_transliteration import sanscript

# Unicode block -> (script name, sanscript scheme)
SCRIPT_BLOCKS: list[tuple[tuple[int, int], str, str]] = [
    ((0x0900, 0x097F), "devanagari", sanscript.DEVANAGARI),
    ((0x0980, 0x09FF), "bengali", sanscript.BENGALI),
    ((0x0A00, 0x0A7F), "gurmukhi", sanscript.GURMUKHI),
    ((0x0A80, 0x0AFF), "gujarati", sanscript.GUJARATI),
    ((0x0B00, 0x0B7F), "oriya", sanscript.ORIYA),
    ((0x0B80, 0x0BFF), "tamil", sanscript.TAMIL),
    ((0x0C00, 0x0C7F), "telugu", sanscript.TELUGU),
    ((0x0C80, 0x0CFF), "kannada", sanscript.KANNADA),
    ((0x0D00, 0x0D7F), "malayalam", sanscript.MALAYALAM),
]
SCHEME_BY_SCRIPT = {name: scheme for _, name, scheme in SCRIPT_BLOCKS}

# Zero-width joiners split words invisibly (ಎಚ್‌ಡಿಎಫ್‌ಸಿ); BOM / soft hyphen are noise.
_INVISIBLE = dict.fromkeys(map(ord, "‌‍﻿­"), None)
# Malayalam "chillu" letters are standalone final consonants the transliterator does not know:
# rewrite them as consonant + virama, which it does.
_CHILLU = {"ൺ": "ണ്", "ൻ": "ന്", "ർ": "ര്",
           "ൽ": "ല്", "ൾ": "ള്", "ൿ": "ക്"}


def script_of(ch: str) -> str | None:
    """Name of the Indic script a character belongs to, or None (Latin, digits, punctuation...)."""
    cp = ord(ch)
    for (lo, hi), name, _ in SCRIPT_BLOCKS:
        if lo <= cp <= hi:
            return name
    return None


def dominant_script(text: str) -> str:
    """Most frequent Indic script in `text`, else 'latin'."""
    counts: dict[str, int] = {}
    for ch in text:
        s = script_of(ch)
        if s:
            counts[s] = counts.get(s, 0) + 1
    return max(counts, key=counts.get) if counts else "latin"


# Devanagari "candra" vowels mark English loanwords (कॉल call, डॉक्टर doctor, ऑफिस office, बॅंक bank).
# The transliterator does not know them; map to the nearest standard vowel.
_CANDRA = {"ॉ": "ो", "ऑ": "ओ", "ॅ": "े", "ऍ": "ए"}


def clean(text: str) -> str:
    """Remove invisible characters and expand characters the transliterator cannot handle."""
    text = text.translate(_INVISIBLE)
    for table in (_CHILLU, _CANDRA):
        for ch, rep in table.items():
            text = text.replace(ch, rep)
    return text
