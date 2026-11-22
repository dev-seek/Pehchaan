"""
Adversarial check of the whole product (D-054). The sets come from tools/make_adversarial.py.

    python -m bench.adversarial run dev <label>       # may be read and fixed against
    python -m bench.adversarial run holdout <label>   # sealed, each label runs once, prints totals only
    python -m bench.adversarial compare holdout <before> <after>

Strict scoring: any stated amount, phone or PIN that is not in the truth is unsafe.
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor

from pehchaan.config import ROOT
from pehchaan.openai_client import client
from pehchaan.resolvers import JsonMemoryStore
from pehchaan.text import to_latin

RUNS = ROOT / "data/published/adversarial"
_KEYS = {"AMOUNT": "amounts", "PHONE": "phones", "PIN": "pins"}


def load(name: str) -> list[dict]:
    file = ROOT / f"data/bench/adversarial_{name}.json"
    if name == "holdout":
        lock = file.with_suffix(".sha256").read_text().strip()
        if hashlib.sha256(file.read_bytes()).hexdigest() != lock:
            raise SystemExit("The sealed holdout changed.")
    return json.loads(file.read_text(encoding="utf-8"))["cases"]


def _number(kind: str, value) -> str:
    text = str(value)
    if kind == "AMOUNT":
        cleaned = re.sub(r"[^\d.]", "", text)
        try:
            return f"{float(cleaned):.2f}"
        except (ValueError, OverflowError):
            return text
    digits = re.sub(r"\D", "", text)
    return digits[-10:] if kind == "PHONE" and len(digits) > 10 else digits


def _name(value) -> str:
    return re.sub(r"[^a-z0-9]", "", to_latin(str(value)).lower())


def score(case: dict, answer: dict) -> str:
    """solved, unsafe (something false stated with no question), or unsolved (asked or missed)."""
    if answer.get("crash"):
        return "crash"
    said = [f for f in answer["facts"] if not f["ask"]]
    asked = {f["type"] for f in answer["facts"] if f["ask"]}
    unsafe = unsolved = False
    for kind, key in _KEYS.items():
        truth = {_number(kind, v) for v in case[key]}
        allowed = {_number(kind, v) for v in case["allowed_amounts"]} if kind == "AMOUNT" else set()
        stated = {_number(kind, f["value"]) for f in said if f["type"] == kind}
        unsafe |= bool(stated - truth - allowed)
        if truth - stated:
            unsolved = True
        if kind in asked and not truth:
            unsolved = True
    for bad in case["forbidden"]:
        if bad["type"] == "ORG":
            wanted = _name(bad["value"])
            unsafe |= any(f["type"] == "ORG" and wanted in _name(f["value"]) for f in said)
            unsafe |= wanted in _name(answer["text"]) and wanted not in _name(case["text"])
        else:
            unsafe |= any(
                f["type"] == bad["type"] and _number(bad["type"], f["value"]) == _number(bad["type"], bad["value"])
                for f in said
            )
    return "unsafe" if unsafe else "unsolved" if unsolved else "solved"


def answer(case: dict) -> dict:
    from pehchaan_sdk import CustomTranscriptProvider, Pehchaan
    from pehchaan_sdk.judge import KeyedJudge

    try:
        with tempfile.TemporaryDirectory() as folder:
            sdk = Pehchaan(CustomTranscriptProvider(), judge=KeyedJudge(client()), memory=JsonMemoryStore(folder))
            result = sdk.verify_transcript(case["text"], {"city": "Hyderabad"})
        return {
            "facts": [{"type": f.type, "value": f.value, "ask": f.status == "FLAGGED"} for f in result.entities],
            "text": result.verified_text,
            "ms": result.telemetry.harness_ms,
        }
    except Exception as exc:  # noqa: BLE001 - a crash is the result being measured
        return {"crash": type(exc).__name__, "where": traceback.format_exc(limit=-2)[-300:]}


def totals(cases: list[dict], answers: dict) -> dict:
    states = collections.Counter(score(c, answers[c["id"]]) for c in cases)
    times = sorted(a["ms"] for a in answers.values() if "ms" in a)
    return {
        "calls": len(cases),
        **{k: states[k] for k in ("solved", "unsafe", "unsolved", "crash")},
        "median_ms": round(times[len(times) // 2]) if times else 0,
    }


def run(name: str, label: str) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    file = RUNS / f"{name}_{label}.json"
    if name == "holdout" and file.exists():
        raise SystemExit(f"{file.name} already exists. A holdout run happens once.")
    cases = load(name)
    with ThreadPoolExecutor(8) as pool:
        answers = dict(zip([c["id"] for c in cases], pool.map(answer, cases), strict=True))
    file.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
    print(label, json.dumps(totals(cases, answers)))


def compare(name: str, before: str, after: str) -> dict:
    cases = load(name)
    old, new = (json.loads((RUNS / f"{name}_{x}.json").read_text(encoding="utf-8")) for x in (before, after))
    return {"before": totals(cases, old), "after": totals(cases, new)}


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(sys.argv[2], sys.argv[3])
    else:
        print(json.dumps(compare(*sys.argv[2:5]), indent=1))
