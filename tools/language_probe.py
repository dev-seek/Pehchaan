"""
What can the frozen engine read in each language? Runs one invented call per language, offline, with no model.

    .venv/bin/python tools/language_probe.py          # writes data/published/language_support.json

This is a capability smoke test on text. It says nothing about how well a speech model hears that language.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pehchaan.languages import get_registry  # noqa: E402
from pehchaan.resolvers import NullMemoryStore  # noqa: E402
from pehchaan_sdk import CustomTranscriptProvider, Pehchaan  # noqa: E402

SOURCE = ROOT / "data" / "probes" / "language_probe.yaml"
OUTPUT = ROOT / "data" / "published" / "language_support.json"


def _outcome(facts, etype: str, expected: str) -> str:
    """right: read correctly. asked: flagged, so a person checks it. missed: not found. wrong: a wrong value, unflagged."""
    found = [f for f in facts if f.type == etype]
    if not found:
        return "missed"
    if any(f.value == expected and f.status != "FLAGGED" for f in found):
        return "right"
    return "asked" if all(f.status == "FLAGGED" for f in found) else "wrong"


def _tier(row: dict, facts: dict, has_pack: bool) -> str:
    if row["evidence"] == "real_voice":
        return "measured"
    if row["evidence"] == "synthetic" and has_pack:
        return "built"
    readable = facts["name"] == "right" and facts["place"] in ("right", "asked")
    return "partial" if row["family"] == "indic" and readable else "unsupported"


def probe() -> dict:
    spec = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    expected, packs = spec["expected"], set(get_registry().packs)
    out = []
    for row in spec["languages"]:
        sdk = Pehchaan(CustomTranscriptProvider(), judge=None, memory=NullMemoryStore(), **spec["context"])
        code = None if row["code"] == "hl" else row["code"]
        call = sdk.verify_transcript(row["call"], language=code).entities
        money = [
            _outcome(sdk.verify_transcript(text, language=code).entities, "AMOUNT", want)
            for text, want in zip(row["money"], expected["money"], strict=True)
        ]
        facts = {
            "name": _outcome(call, "PERSON", expected["person"]),
            "place": _outcome(call, "PLACE", expected["place"]),
            "phone_digits": _outcome(call, "PHONE", expected["phone"]),
            "money_words": sum(m == "right" for m in money),
            "money_wrong": sum(m == "wrong" for m in money),
        }
        has_pack = row["code"] in packs or row["code"] == "hl"
        out.append(
            {k: row[k] for k in ("code", "name", "script")}
            | {"speech_hint": row.get("speech_hint", True), "has_pack": has_pack, "evidence": row["evidence"], "tier": _tier(row, facts, has_pack), "facts": facts}
        )
    return {
        "note": "One invented text call per language, machine-written and not reviewed by native speakers. A capability check, not accuracy.",
        "money_checks": len(expected["money"]),
        "languages": out,
    }


if __name__ == "__main__":
    report = probe()
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for r in report["languages"]:
        f = r["facts"]
        print(
            f"{r['name']:<15}{r['tier']:<12} name={f['name']:<7} place={f['place']:<7} digits={f['phone_digits']:<7} money={f['money_words']}/2 wrong={f['money_wrong']}"
        )
