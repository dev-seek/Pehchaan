"""
World knowledge that is not tied to one language: brands (with SMS sender IDs), city localities, PIN prefixes.
Loaded from data/lexicons/*.yaml. Extend the YAML files; nothing in code names a specific brand or place.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from ..config import path, settings
from ..languages import get_registry
from ..text import normalize


@dataclass(frozen=True)
class Brand:
    name: str
    kind: str
    sender_ids: tuple[str, ...]
    aliases: tuple[str, ...]


@lru_cache(maxsize=1)
def brands() -> tuple[Brand, ...]:
    raw = yaml.safe_load((path("lexicons") / "brands.yaml").read_text(encoding="utf-8"))
    return tuple(Brand(b["name"], b.get("kind", ""), tuple(b.get("sender_ids", [])), tuple(b.get("aliases", [])))
                 for b in raw)


@lru_cache(maxsize=1)
def _brand_by_sender() -> dict[str, Brand]:
    return {sid.upper(): b for b in brands() for sid in b.sender_ids}


def brand_for_sender(sender: str) -> Brand | None:
    """'VM-HDFCBK' or 'HDFCBK' -> Brand('HDFC Bank')."""
    return _brand_by_sender().get(sender.upper().split("-")[-1].strip())


def brand_by_name(name: str) -> Brand | None:
    n = normalize(name)
    for b in brands():
        if n == normalize(b.name) or n in {normalize(a) for a in b.aliases} or normalize(b.name).startswith(n):
            return b
    return None


@lru_cache(maxsize=1)
def short_names() -> dict[str, tuple[str, ...]]:
    """
    'HDFC Bank' -> ('HDFC',): callers drop generic words. Kept only if the short form is unique across brands,
    at least `min_letters` long, not an everyday word ("Yes Bank" gets no "Yes"), and not ending in a glue word.
    """
    cfg = settings()["lexicon"]
    generic = {w.lower() for w in cfg["generic_brand_words"]}
    reg = get_registry()
    owners: dict[str, list[tuple[str, str]]] = {}
    for b in brands():
        words = b.name.split()
        while len(words) > 1 and words[-1].lower() in generic:
            words = words[:-1]
        head = " ".join(words)
        if head == b.name or len(head.replace(" ", "")) < cfg["short_name_min_letters"]:
            continue
        if reg.is_glue(normalize(words[-1])) or reg.is_everyday(normalize(head)):
            continue
        owners.setdefault(head.lower(), []).append((b.name, head))
    return {pairs[0][0]: (pairs[0][1],) for pairs in owners.values() if len(pairs) == 1}


@lru_cache(maxsize=1)
def _cities() -> dict:
    return yaml.safe_load((path("lexicons") / "localities.yaml").read_text(encoding="utf-8"))


def city_names() -> list[str]:
    return list(_cities())


def localities(city: str | None) -> list[str]:
    return list(_cities().get(city, {}).get("localities", [])) if city else []


def pin_prefixes(city: str | None) -> list[str]:
    return [str(p) for p in _cities().get(city, {}).get("pin_prefixes", [])] if city else []
