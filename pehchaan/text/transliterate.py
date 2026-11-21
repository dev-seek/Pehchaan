"""
Indic script -> Latin, the way Indians type Hinglish/Tenglish ("कोंडापुर" -> "kondaapur").

Pipeline per script run:  clean()  ->  sanscript to IAST  ->  script-specific fixes  ->  IAST to Hinglish letters.
Script-specific fixes:
  * Devanagari/Gurmukhi/Gujarati: Hindi schwa deletion (the written-but-silent 'a': कमल = kamal, करना = karnaa)
  * Tamil: the script uses one letter for k/g, t/d, p/b and has no aspiration; the converter outputs voiced
    aspirated forms (கொண்டாபூர் -> "ghondhaabhoor"), so we de-aspirate and make word-initial stops voiceless.
"""
from __future__ import annotations

import re
import unicodedata

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

from .scripts import SCHEME_BY_SCRIPT, clean, script_of

SCHWA_DELETING_SCRIPTS = {"devanagari", "gurmukhi", "gujarati"}

_IAST_CONS = ["kh", "gh", "ch", "jh", "ṭh", "ḍh", "th", "dh", "ph", "bh", "k", "g", "ṅ", "c", "j", "ñ", "ṭ",
              "ḍ", "ṇ", "t", "d", "n", "p", "b", "m", "y", "r", "l", "v", "ś", "ṣ", "s", "h", "ḻ", "z", "f", "q"]
_IAST_VOW = ["ai", "au", "ā", "ī", "ū", "ṝ", "ṛ", "ḷ", "a", "i", "u", "e", "o", "ē", "ō"]
_IAST_MOD = ["m̐", "ṃ", "ḥ", "~"]

_IAST_TO_HINGLISH = {
    "ś": "sh", "ṣ": "sh", "ṃ": "n", "m̐": "n", "~": "n", "ṅ": "n", "ñ": "n", "ṇ": "n", "ṛ": "ri", "ṝ": "ri",
    "ḥ": "h", "ā": "aa", "ī": "ee", "ū": "oo", "ē": "e", "ō": "o", "è": "e", "ò": "o", "ḻ": "l", "r̥": "ri",
}


def _iast_units(word: str) -> list[tuple[str, str]]:
    """Split an IAST word into (kind, unit) with kind C=consonant, V=vowel, M=modifier, X=other."""
    units: list[tuple[str, str]] = []
    i = 0
    while i < len(word):
        for kind, inventory in (("M", _IAST_MOD), ("C", _IAST_CONS), ("V", _IAST_VOW)):
            hit = next((u for u in inventory if word.startswith(u, i)), None)
            if hit:
                if hit == "ṛ" and units and units[-1][0] == "V":   # ड़ after a vowel is a consonant in Hindi
                    kind = "C"
                units.append((kind, hit))
                i += len(hit)
                break
        else:
            units.append(("X", word[i]))
            i += 1
    return units


def hindi_schwa_deletion(iast_word: str) -> str:
    """Drop silent inherent vowels: final (kamala -> kamal) and medial V C [a] C V, left to right (karanā -> karnā)."""
    u = _iast_units(iast_word)
    if len(u) < 3:
        return iast_word
    if u[-1] == ("V", "a") and u[-2][0] == "C":
        u = u[:-1]
    i = 2
    while i < len(u) - 2:
        if u[i] == ("V", "a") and u[i - 1][0] == "C" and u[i - 2][0] == "V" \
                and u[i + 1][0] == "C" and u[i + 2][0] == "V":
            u = u[:i] + u[i + 1:]
        i += 1
    return "".join(x for _, x in u)


def _tamil_fix(latin_word: str) -> str:
    w = re.sub(r"([kgcjtdpb])h", r"\1", latin_word)          # no aspiration in Tamil
    return re.sub(r"^g", "k", re.sub(r"^d", "t", re.sub(r"^b", "p", re.sub(r"^j", "s", w))))


def _iast_word_to_hinglish(word: str, script: str) -> str:
    w = hindi_schwa_deletion(word) if script in SCHWA_DELETING_SCRIPTS else word
    w = w.replace("ch", "\x00").replace("c", "ch").replace("\x00", "chh")   # IAST c=च (typed ch), ch=छ (chh)
    for a, b in _IAST_TO_HINGLISH.items():
        w = w.replace(a, b)
    w = unicodedata.normalize("NFKD", w)
    w = "".join(c for c in w if not unicodedata.combining(c))
    return _tamil_fix(w) if script == "tamil" else w


def to_latin(text: str) -> str:
    """Convert every Indic-script run in `text` to Hinglish-style Latin; everything else passes through."""
    text = clean(text)
    out: list[str] = []
    buf: list[str] = []
    buf_script: str | None = None

    def flush() -> None:
        nonlocal buf, buf_script
        if buf:
            iast = transliterate("".join(buf), SCHEME_BY_SCRIPT[buf_script], sanscript.IAST)
            out.append("".join(_iast_word_to_hinglish(x, buf_script) if x.strip() else x
                               for x in re.split(r"(\s+)", iast)))
        buf, buf_script = [], None

    for ch in text:
        s = script_of(ch)
        if s is None:
            flush()
            out.append(" " if ch in "।॥" else ch)
            continue
        if buf_script not in (None, s):
            flush()
        buf_script = s
        buf.append(ch)
    flush()
    return "".join(out)
