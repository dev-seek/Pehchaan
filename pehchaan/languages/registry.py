"""
The LanguageRegistry merges all ACTIVE language packs into one set of lookups.

Why merge instead of picking one pack per call? Indian callers mix languages inside a single sentence
("mera number nine eight four… పంపండి"). So every layer asks the registry ("is this a number word? a cue? an
everyday word?") and gets the answer from ALL active packs at once. Where language really matters (the
clarifying question we speak back), languages.detect picks the dominant language of the utterance.

Conflicts fail fast: if two packs give the same word different number values, loading stops with a clear error.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from functools import lru_cache

from ..config import path, settings
from ..sound import key
from .pack import MARKER_KINDS, LanguagePack, load_pack

MIN_COMMON_KEY_LETTERS = 4   # shorter sound keys collide with real names, so they match by exact spelling only


class PackConflictError(ValueError):
    """Two active packs disagree about the same word."""


class LanguageRegistry:
    def __init__(self, packs: Iterable[LanguagePack], default: str = "en"):
        self.packs: dict[str, LanguagePack] = {p.code: p for p in packs}
        if not self.packs:
            raise ValueError("no language packs loaded")
        self.order = list(self.packs)
        self.default = default if default in self.packs else self.order[0]
        self._numbers = self._merge(lambda p: p.number_words, "number word")
        self._multipliers = self._merge(lambda p: p.multipliers, "multiplier")
        self._fractions = self._merge(lambda p: p.fractions, "fraction")
        self._shifts = self._merge(lambda p: p.shift_modifiers, "shift modifier")
        self._repeaters = self._merge(lambda p: p.repeaters, "repeater")
        self._weak = frozenset().union(*(p.weak_words for p in self.packs.values()))
        self._teen_ty: dict[str, str] = {}
        for p in self.packs.values():
            for teen, ty in p.teen_ty_pairs:
                self._teen_ty[teen], self._teen_ty[ty] = ty, teen
        self._cues = {kind: frozenset().union(*(p.cues.get(kind, frozenset()) for p in self.packs.values()))
                      for kind in ("PHONE", "PIN", "AMOUNT", "CURRENCY")}
        self._everyday = frozenset().union(*(p.everyday_words for p in self.packs.values()))
        self._everyday_keys = frozenset(k for k in (key(w) for w in self._everyday) if k)
        self._glue = frozenset().union(*(p.glue_words for p in self.packs.values()))
        self._common = frozenset().union(*(p.common_words for p in self.packs.values()))
        self._common_keys = frozenset(k for k in (key(w) for w in self._common) if len(k) >= MIN_COMMON_KEY_LETTERS)
        self._markers = {kind: frozenset().union(*(p.markers.get(kind, frozenset()) for p in self.packs.values()))
                         for kind in MARKER_KINDS}
        self._fact_cues = {kind: frozenset().union(*(p.fact_cues.get(kind, frozenset()) for p in self.packs.values()))
                           for kind in ("PHONE", "PIN")}
        letter_forms = {form: letter for p in self.packs.values() for form, letter in p.letter_names.items()}
        self._letters = sorted(letter_forms.items(), key=lambda item: -len(item[0]))   # longest form first
        self._vocab = self._build_vocab()

    # ---- construction helpers ------------------------------------------------------------------
    def _merge(self, get: Callable[[LanguagePack], Mapping[str, float]], what: str) -> dict[str, float]:
        merged: dict[str, float] = {}
        owner: dict[str, str] = {}
        for p in self.packs.values():
            for word, value in get(p).items():
                if word in merged and merged[word] != value:
                    raise PackConflictError(f"{what} '{word}' = {merged[word]} in '{owner[word]}' "
                                            f"but {value} in '{p.code}'. Fix one of the packs.")
                merged[word], owner[word] = value, p.code
        return merged

    def _build_vocab(self) -> dict[str, set[str]]:
        vocab: dict[str, set[str]] = {}
        for p in self.packs.values():
            words = set(p.number_words) | set(p.multipliers) | p.everyday_words | p.glue_words
            for cue_words in p.cues.values():
                words |= cue_words
            for w in words:
                vocab.setdefault(w, set()).add(p.code)
        return vocab

    # ---- numbers --------------------------------------------------------------------------------
    def number_value(self, w: str) -> int | None:
        v = self._numbers.get(w)
        return None if v is None else int(v)

    def multiplier(self, w: str) -> int | None:
        v = self._multipliers.get(w)
        return None if v is None else int(v)

    def fraction(self, w: str) -> float | None:
        return self._fractions.get(w)

    def shift_modifier(self, w: str) -> float | None:
        return self._shifts.get(w)

    def repeater(self, w: str) -> int | None:
        v = self._repeaters.get(w)
        return None if v is None else int(v)

    def is_weak_number(self, w: str) -> bool:
        return w in self._weak

    def teen_ty_swap(self, w: str) -> str | None:
        return self._teen_ty.get(w)

    # ---- cues and word classes ------------------------------------------------------------------
    def cue_words(self, kind: str) -> frozenset[str]:
        return self._cues.get(kind, frozenset())

    def is_everyday(self, w: str) -> bool:
        """Everyday word in ANY active language; matched by spelling or by sound (हैलो = hello)."""
        return w in self._everyday or key(w) in self._everyday_keys

    def is_glue(self, w: str) -> bool:
        return w in self._glue

    def is_common(self, w: str) -> bool:
        """Ordinary vocabulary (or an everyday word), by spelling or by sound: must not silently become an entity."""
        return w in self._common or key(w) in self._common_keys or self.is_everyday(w)

    def marker_words(self, kind: str) -> frozenset[str]:
        return self._markers[kind]

    def fact_cues(self, kind: str) -> frozenset[str]:
        return self._fact_cues[kind]

    # ---- language routing -----------------------------------------------------------------------
    def languages_of_word(self, w: str) -> set[str]:
        return self._vocab.get(w, set())

    def language_for_script(self, script: str, word: str) -> str | None:
        """Language of a word written in an Indic script (vocabulary breaks ties between same-script packs)."""
        owners = [c for c in self.order if script in self.packs[c].scripts]
        if len(owners) > 1:
            known = [c for c in owners if c in self.languages_of_word(word)]
            owners = known or owners
        return owners[0] if owners else None

    def decode_spelled_acronym(self, word: str, min_letters: int = 3) -> str | None:
        """'echadeeephasee' -> 'hdfc' when the WHOLE word splits into spelled English letter names."""
        n = len(word)
        best: list[str | None] = [None] * (n + 1)
        best[0] = ""
        for i in range(n):
            if best[i] is None:
                continue
            for form, letter in self._letters:
                j = i + len(form)
                if word.startswith(form, i) and (best[j] is None or len(best[i]) + 1 < len(best[j])):
                    best[j] = best[i] + letter
        out = best[n]
        return out if out and len(out) >= min_letters else None

    def clarify_template(self, lang: str, etype: str, arity: str) -> str | None:
        """Question template for (language, entity type, 'two'|'one'|'none'), falling back to the default language."""
        for code in (lang, self.default):
            t = self.packs.get(code)
            if t and etype in t.clarify and arity in t.clarify[etype]:
                return t.clarify[etype][arity]
        return None


@lru_cache(maxsize=1)
def get_registry() -> LanguageRegistry:
    """The registry for the languages listed in settings.yaml `languages.active`."""
    cfg = settings()["languages"]
    packs = [load_pack(path("languages") / f"{code}.yaml") for code in cfg["active"]]
    return LanguageRegistry(packs, default=cfg.get("default", "en"))
