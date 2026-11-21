"""Script-independent name matching.

Every script is mapped to one small phoneme alphabet; names match when a weighted
edit distance (cheap vowels, dear consonants) is under a YAML threshold.
"""
from __future__ import annotations

import functools
import re
import unicodedata
from difflib import SequenceMatcher

import yaml

from .numbers import _DROP, YAML_PATH

VOWELS = "aeiou"


@functools.lru_cache(maxsize=1)
def _cfg() -> dict:
    cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))["names"]

    def pairs(s: str) -> dict[str, str]:
        return dict(p.split("=", 1) for p in s.split())

    for sc in cfg["scripts"].values():
        for k in ("cons", "indep", "signs"):
            sc[k] = pairs(sc[k])
        sc["nasal"], sc["visarga"] = set(sc["nasal"].split()), set(sc["visarga"].split())
    ar = cfg["arabic"]
    ar["cons"] = pairs(ar["cons"])
    for k in ("alef", "waw", "yeh", "barree", "heh", "ignore"):
        ar[k] = set(ar[k].split())
    cfg["letters"] = pairs(cfg["letter_names"])
    cfg["rules"] = [(re.compile(p), r) for p, r in cfg["latin_rules"]]
    return cfg


def _script_of(ch: str) -> str:
    cp, cfg = ord(ch), _cfg()
    for name, sc in cfg["scripts"].items():
        if sc["range"][0] <= cp <= sc["range"][1]:
            return name
    if cfg["kannada_range"][0] <= cp <= cfg["kannada_range"][1]:
        return "telugu"
    if any(a <= cp <= b for a, b in cfg["arabic"]["ranges"]):
        return "arabic"
    return "latin"


def _latin(word: str) -> str:
    cfg = _cfg()
    s = unicodedata.normalize("NFKD", word.lower())
    s = "".join(c for c in s if ord(c) not in _DROP and c.isalpha())
    for pat, rep in cfg["rules"]:
        s = pat.sub(rep, s)
    return re.sub(r"(.)\1+", r"\1", s)


def _brahmic(word: str, name: str) -> str:
    sc = _cfg()["scripts"][name]
    chars = [chr(ord(c) - 0x80) if _script_of(c) == "telugu" and ord(c) >= 0x0C80 else c
             for c in unicodedata.normalize("NFD", word)]
    chars = [c for c in chars if ord(c) not in _DROP]
    out, i, n = [], 0, len(chars)
    while i < n:
        c = chars[i]
        if c in sc["cons"]:
            out.append(sc["cons"][c])
            nxt = chars[i + 1] if i + 1 < n else ""
            if nxt == sc["virama"]:
                i += 1
            elif nxt in sc["signs"]:
                out.append(sc["signs"][nxt])
                i += 1
            elif nxt or sc["final_schwa"]:
                out.append("a")
        elif c in sc["indep"]:
            out.append(sc["indep"][c])
        elif c in sc["nasal"]:
            out.append("N")
        elif c in sc["visarga"]:
            out.append("h")
        i += 1
    s = "".join(out)
    if sc.get("final_anusvara_is_m") and s.endswith("N"):     # సుందరం = sundaram
        s = s[:-1] + "m"
    s = re.sub(r"N(?=[pbm])", "m", s).replace("N", "n")
    return re.sub(r"(.)\1+", r"\1", s)


def _arabic(word: str) -> str:
    ar = _cfg()["arabic"]
    chars = [c for c in unicodedata.normalize("NFC", word) if ord(c) not in _DROP and c not in ar["ignore"]]
    out = []
    for i, c in enumerate(chars):
        prev_v = i > 0 and chars[i - 1] in ar["alef"]
        if c in ar["cons"]:
            out.append(ar["cons"][c])
        elif c in ar["alef"]:
            out.append("a")
        elif c in ar["waw"]:
            out.append("v" if i == 0 or prev_v else "u")
        elif c in ar["yeh"]:
            out.append("y" if i == 0 or prev_v else "i")
        elif c in ar["barree"]:
            out.append("e")
        elif c in ar["heh"]:
            out.append("a" if i == len(chars) - 1 else "h")
    return re.sub(r"(.)\1+", r"\1", "".join(out))


@functools.lru_cache(maxsize=20000)
def phon(word: str) -> tuple[str, bool]:
    """(phoneme string, from_abjad) for one token; all-caps / vowel-less Latin is spelled as letters."""
    letters = _cfg()["letters"]
    if word.isascii() and word.isalpha() and 2 <= len(word) <= 5 and (
            word.isupper() or not re.search("[aeiouy]", word.lower())):
        return "".join(letters[c] for c in word.lower()), False
    out, abjad, i = [], False, 0
    while i < len(word):
        sc = _script_of(word[i])
        j = i
        while j < len(word) and (_script_of(word[j]) == sc or unicodedata.category(word[j])[0] == "M"):
            j += 1
        seg = word[i:j]
        if sc == "latin":
            out.append(_latin(seg))
        elif sc == "arabic":
            out.append(_arabic(seg))
            abjad = True
        else:
            out.append(_brahmic(seg, sc))
        i = j
    return "".join(out), abjad


def _is_vowel(c: str) -> bool:
    return c in VOWELS


def _indel(s: str, i: int, abjad: bool, k: dict) -> float:
    c = s[i]
    if _is_vowel(c):
        return k["abjad_vowel"] if abjad else (k["schwa"] if c == "a" else k["vowel"])
    if c == "h":
        return k["aspirate"]
    if c == "y" and i > 0 and not _is_vowel(s[i - 1]):
        return k["post_consonant_glide"]
    if c in "yv":
        return k["glide"]
    if c in "nm" and i + 1 < len(s) and not _is_vowel(s[i + 1]):
        return k["nasal"]
    return k["unrelated_consonant"]


def _sub(a: str, b: str, abjad: bool, k: dict, conf: set) -> float:
    if a == b:
        return 0.0
    if _is_vowel(a) and _is_vowel(b):
        return k["abjad_vowel"] if abjad else k["vowel"]
    if {a, b} in conf:
        return k["confusable"]
    if (_is_vowel(a) and b in "yv") or (_is_vowel(b) and a in "yv"):
        return k["glide_vowel_sub"]
    return k["unrelated_consonant"]


def distance(a: str, b: str, abjad: bool = False) -> float:
    """Normalised weighted edit distance between two phoneme strings."""
    cfg = _cfg()
    k = cfg["cost"]
    conf = {frozenset(p.split()) for p in cfg["confusable"]}
    prev = [0.0]
    for i in range(len(b)):
        prev.append(prev[-1] + _indel(b, i, abjad, k))
    for i, ca in enumerate(a):
        cur = [prev[0] + _indel(a, i, abjad, k)]
        for j, cb in enumerate(b):
            cur.append(min(prev[j] + _sub(ca, cb, abjad, k, conf),
                           prev[j + 1] + _indel(a, i, abjad, k),
                           cur[j] + _indel(b, j, abjad, k)))
        prev = cur
    cons = max(sum(not _is_vowel(c) for c in a), sum(not _is_vowel(c) for c in b))
    return prev[-1] / max(cons, cfg["min_denominator"])


def _tokens(text: str) -> list[str]:
    out, cur = [], ""
    for ch in text:
        if unicodedata.category(ch)[0] in "LM":
            cur += ch
        elif cur:
            out.append(cur)
            cur = ""
    return out + ([cur] if cur else [])


def _join(words: list[str]) -> tuple[str, bool]:
    ps = [phon(w) for w in words]
    return "".join(p for p, _ in ps), any(a for _, a in ps)


def _first_vowel_conflict(a: str, b: str) -> bool:
    """Karan/Kiran: the first vowel carries a name's identity, so a change of vowel class is a different name."""
    va, vb = next((c for c in a if _is_vowel(c)), ""), next((c for c in b if _is_vowel(c)), "")
    if not va or not vb:
        return False
    classes = _cfg()["vowel_classes"]
    return not any(va in group.split() and vb in group.split() for group in classes)


def _matches(a: str, b: str, abjad: bool) -> bool:
    if not abjad and _first_vowel_conflict(a, b):      # Perso-Arabic script leaves short vowels unwritten
        return False
    return distance(a, b, abjad) <= _cfg()["threshold"]


def same_name(a: str, b: str) -> bool:
    """True when a and b are the same name modulo spelling/script, not a mishearing."""
    pa, aa = _join(_tokens(a))
    pb, ab = _join(_tokens(b))
    if not pa or not pb:
        return False
    return _matches(pa, pb, aa or ab)


def loosely_same(a: str, b: str) -> bool:
    """Could `a` be a garbled hearing of `b`? Used only to credit a flag to the fact it asks about."""
    pa, aa = _join(_tokens(a))
    pb, ab = _join(_tokens(b))
    if not pa or not pb:
        return False
    cfg = _cfg()
    return SequenceMatcher(None, pa, pb, autojunk=False).ratio() >= cfg["flag_credit_min_ratio"]


def name_present(name: str, text: str) -> bool:
    """True when some run of consecutive tokens in text is the same name."""
    cfg = _cfg()
    want = _tokens(name)
    toks = _tokens(text)
    if not want or not toks:
        return False
    pn, an = _join(want)
    phons = [phon(t) for t in toks]
    for i in range(len(toks)):
        buf, abj = "", an
        for j in range(i, min(len(toks), i + len(want) + cfg["window_extra"])):
            buf += phons[j][0]
            abj = abj or phons[j][1]
            if len(buf) > 1.8 * len(pn) + 3:
                break
            if _matches(buf, pn, abj):
                return True
    return False
