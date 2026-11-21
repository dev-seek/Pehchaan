"""Independent number reader: digits, spoken digits, spoken values, mixed forms.

Segments text into word units and number-run units; a run yields a digit string
(for phone/PIN checks) and a value (for amounts). Word lists live in the YAML.
"""
from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

YAML_PATH = Path(__file__).resolve().parents[2] / "data" / "bench" / "oracle_numbers.yaml"
BREAKERS = set(".?!।॥;:\n|؟")
_DROP = set(range(0x0300, 0x0370)) | set(range(0x064B, 0x0660)) | {0x0670, 0x093C, 0x200C, 0x200D, 0x0CBC}
_ARABIC = str.maketrans({"ي": "ی", "ك": "ک", "ه": "ہ", "ۃ": "ہ", "ے": "ی", "ۓ": "ی", "آ": "ا",
                         "أ": "ا", "إ": "ا", "ँ": "ं", "ة": "ہ"})


def fold(word: str) -> str:
    """Spelling-variant fold used for table lookup (nukta, diacritics, Latin long vowels)."""
    s = unicodedata.normalize("NFD", word.lower())
    s = "".join(c for c in s if ord(c) not in _DROP).translate(_ARABIC)
    if s.isascii():
        s = re.sub(r"([^aeiou])\1+", r"\1", s)
        s = s.replace("chh", "ch").replace("ee", "i").replace("oo", "u").replace("w", "v").replace("z", "j")
        s = re.sub(r"(?<=[aeiou])h$", "", s) if len(s) > 3 else s
    return s


def light(word: str) -> str:
    """Light normalisation for diffing: case, nukta and diacritics only."""
    s = unicodedata.normalize("NFD", word.casefold())
    return unicodedata.normalize("NFC", "".join(c for c in s if ord(c) not in _DROP)).translate(_ARABIC)


@dataclass
class Tok:
    text: str
    kind: str            # lit n m f dbl glue w brk
    value: float = 0.0
    plain: bool = True   # literal made only of digits (no comma / decimal point)
    additive: bool = False
    digits: str = ""
    money: bool = False  # written with a rupee sign


@dataclass
class Unit:
    """One diff unit: a word, or a whole number run."""
    surface: str
    is_number: bool = False
    digits: str = ""
    value: float | None = None
    money: bool = False

    @property
    def key(self) -> str:
        if self.is_number:
            return "#" + (self.digits or repr(self.value))
        return light(self.surface)


@dataclass
class NumberFacts:
    digit_strings: set[str] = field(default_factory=set)
    values: set[float] = field(default_factory=set)


@functools.lru_cache(maxsize=1)
def _tables() -> dict:
    cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))["numbers"]
    words: dict[str, tuple] = {}
    for seq in cfg["sequences"]:
        for i, entry in enumerate(seq["entries"]):
            for w in str(entry).split():
                words[fold(w)] = ("n", seq["start"] + i * seq["step"], seq["additive"])
    for mult, ws in cfg["multipliers"].items():
        for w in ws.split():
            words[fold(w)] = ("m", float(mult), False)
    for name, spec in cfg["fractions"].items():
        for w in spec["words"].split():
            words[fold(w)] = ("f", spec["add"], name == "sawa")
    for val, ws in cfg["fixed_values"].items():
        for w in ws.split():
            words[fold(w)] = ("n", float(val), False)
    for k, ws in cfg["modifiers"].items():
        for w in ws.split():
            words[fold(w)] = ("dbl", float(k), False)
    words[cfg["glue"]] = ("glue", 0.0, False)
    return words


def _scan(text: str) -> list[Tok]:
    """Split text into tokens: numeric literals, words, and sentence breaks."""
    toks: list[Tok] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        cat = unicodedata.category(ch)
        if cat == "Nd":
            j, buf = i, ""
            while j < n:
                c = text[j]
                if unicodedata.category(c) == "Nd":
                    buf += str(unicodedata.digit(c))
                elif c in ",." and j + 1 < n and unicodedata.category(text[j + 1]) == "Nd" and buf:
                    buf += c
                else:
                    break
                j += 1
            plain = buf.isdigit()
            clean = buf.replace(",", "")
            toks.append(Tok(text[i:j], "lit", float(clean), plain, digits=clean if clean.isdigit() else "",
                            money=text[:i].rstrip().endswith("₹")))
            i = j
        elif cat[0] in "LM":
            j = i
            while j < n and unicodedata.category(text[j])[0] in "LM":
                j += 1
            toks.append(Tok(text[i:j], "w"))
            i = j
        else:
            if ch in BREAKERS:
                toks.append(Tok(ch, "brk"))
            i += 1
    return toks


def _classify(toks: list[Tok]) -> None:
    table = _tables()
    for t in toks:
        if t.kind == "w":
            hit = table.get(fold(t.text))
            if hit:
                t.kind, t.value, t.additive = hit[0], float(hit[1]), bool(hit[2])
    for i, t in enumerate(toks):
        if t.kind == "glue" and not (i and i + 1 < len(toks) and toks[i - 1].kind == "m"
                                     and toks[i + 1].kind in ("n", "lit")):
            t.kind = "w"


def _joins(a: Tok, b: Tok) -> bool:
    if a.kind in ("m", "f", "dbl", "glue") or b.kind in ("m", "glue"):
        return True
    if b.kind == "f":
        return False
    if a.kind == "lit" and b.kind == "lit":
        return a.plain and b.plain
    if a.kind == "lit" or b.kind == "lit":
        word = b if a.kind == "lit" else a
        lit = a if a.kind == "lit" else b
        return lit.plain and word.value < 10
    return True


def _merge_additive(run: list[Tok]) -> list[Tok]:
    out: list[Tok] = []
    for t in run:
        if out and out[-1].kind == "n" and out[-1].additive and t.kind == "n" and not t.additive \
                and 0 < t.value < 10 and out[-1].value % 10 == 0:
            out[-1] = Tok(out[-1].text + " " + t.text, "n", out[-1].value + t.value)
        else:
            out.append(t)
    return out


def _value(run: list[Tok]) -> float:
    total = cur = add = 0.0
    for i, t in enumerate(run):
        if t.kind in ("n", "lit"):
            cur += t.value + add
            add = 0.0
        elif t.kind == "f":
            nxt = run[i + 1].kind if i + 1 < len(run) else ""
            if t.additive and nxt == "m":      # sawa lakh = 1.25 lakh
                cur += 1.25
            else:
                add = t.value
        elif t.kind == "m":
            if t.value == 100:
                cur = (cur or 1.0) * 100
            else:
                total += (cur or 1.0) * t.value
                cur = 0.0
    return total + cur


def _digits(run: list[Tok]) -> str:
    out, rep = "", 1
    for t in run:
        if t.kind == "dbl":
            rep = int(t.value)
        elif t.kind in ("n", "lit"):
            piece = t.digits if t.kind == "lit" else (str(int(t.value)) if t.value == int(t.value) else "")
            out += piece * rep
            rep = 1
    return out


def _run_facts(run: list[Tok]) -> tuple[str, float | None]:
    run = _merge_additive(run)
    body = [t for t in run if t.kind in ("n", "lit", "m")]
    if not body:
        return "", None
    if any(t.kind in ("m", "f") for t in run):
        v = _value(run)
        return (str(int(v)) if v == int(v) else ""), v
    digits = _digits(run)
    if len(body) == 1:
        return digits, body[0].value
    return digits, float(int(digits)) if digits else None


def segment(text: str) -> list[Unit]:
    """Words and number runs, in order; sentence punctuation is dropped."""
    toks = _scan(text)
    _classify(toks)
    units: list[Unit] = []
    i = 0
    while i < len(toks):
        run, j = _grab(toks, i)
        if run and any(x.kind in ("n", "lit", "m") for x in run):
            units.append(_unit(run))
            i = j
            continue
        if toks[i].kind != "brk":
            units.append(Unit(toks[i].text))
        i += 1
    return units


def _grab(toks: list[Tok], i: int) -> tuple[list[Tok], int]:
    numeric = ("lit", "n", "m", "f", "dbl", "glue")
    if toks[i].kind not in numeric:
        return [], i + 1
    j = i + 1
    while j < len(toks) and toks[j].kind in numeric and _joins(toks[j - 1], toks[j]):
        j += 1
    run = toks[i:j]
    while run and run[-1].kind in ("f", "dbl", "glue"):   # dangling modifiers are plain words
        run = run[:-1]
        j -= 1
    return run, j


def _unit(run: list[Tok]) -> Unit:
    digits, value = _run_facts(run)
    return Unit(" ".join(t.text for t in run), True, digits, value, money=any(t.money for t in run))


def read_numbers(text: str) -> NumberFacts:
    facts = NumberFacts()
    for u in segment(text):
        if u.is_number:
            if u.digits and not u.money:         # "₹5,60,007" states money, not a PIN or a phone number
                facts.digit_strings.add(u.digits)
            if u.value is not None:
                facts.values.add(float(u.value))
    return facts


def number_fact(entity: dict, text: str) -> bool:
    """PHONE/PIN: an exact run equals the digits (+91 / 0 prefix ignored). AMOUNT: a value equals it."""
    facts = read_numbers(text)
    want = re.sub(r"\D", "", str(entity["value"])) if entity["type"] != "AMOUNT" else ""
    if entity["type"] == "AMOUNT":
        try:
            return float(str(entity["value"]).replace(",", "")) in facts.values
        except ValueError:
            return False
    for d in facts.digit_strings:
        if d == want or (len(want) == 10 and ((len(d) == 12 and d[:2] == "91" and d[2:] == want)
                                              or (len(d) == 11 and d[0] == "0" and d[1:] == want))):
            return True
    return False
