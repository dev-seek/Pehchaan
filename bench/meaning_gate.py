"""
The ship-or-stop gate for the meaning layer (D-052). The rules are in docs/MEANING_GATE.md and were written first.

    python -m bench.meaning_gate run baseline    # the build that stays live if the gate fails
    python -m bench.meaning_gate run candidate   # the same build plus the meaning layer
    python -m bench.meaning_gate verdict         # applies the rules once

A run stores its answers and prints no per-case detail, so nothing can be tuned on the fresh set. The exam is never read.
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

from pehchaan.config import ROOT
from pehchaan.judge import OpenAIJudge
from pehchaan.openai_client import client
from pehchaan.resolvers import JsonMemoryStore
from pehchaan.sound import key
from pehchaan.text import to_latin

NUMBERS = {"PHONE", "PIN", "AMOUNT"}
ATTACK = ROOT / "data/bench/meaning_attack.json"
RUNS = ROOT / "results/meaning_gate"
RECORDED = ("dev_normal", "dev_misleading", "real_voice")


def load_attack() -> dict:
    lock = ATTACK.with_suffix(".sha256").read_text().strip()
    if hashlib.sha256(ATTACK.read_bytes()).hexdigest() != lock:
        raise SystemExit("The fresh attack set changed after it was locked.")
    return json.loads(ATTACK.read_text(encoding="utf-8"))


def _truth(entities: list[dict]) -> list[list]:
    return [["right", e["type"], e["value"]] for e in entities]


def load_sets() -> dict[str, list[dict]]:
    attack = load_attack()
    out = {"fresh_attacks": [{**c, "ctx": attack["context"]} for c in attack["cases"]]}
    scripts = {
        s["script_id"]: s for s in map(json.loads, (ROOT / "data/bench/dev_scripts.jsonl").open(encoding="utf-8"))
    }
    latest = json.loads((ROOT / "results/latest_dev.json").read_text())["dir"]
    clips: dict[str, dict] = collections.defaultdict(dict)
    for line in (ROOT / latest / "per_clip.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        clips[row["clip_id"]][row["system"]] = row
    for name, system, field in (
        ("dev_normal", "P_on_B1_C3", "context"),
        ("dev_misleading", "P_on_B1_C4", "context_adv"),
    ):
        out[name] = [
            {
                "id": clip,
                "text": rows[system]["in_text"],
                "alt": rows["B0_asr_plain"]["text"],
                "ctx": scripts[clip.split("__")[0]][field],
                "truth": _truth(scripts[clip.split("__")[0]]["entities"]),
            }
            for clip, rows in clips.items()
        ]
    samples = {s["id"]: s for s in json.loads((ROOT / "data/demo/real_samples.json").read_text(encoding="utf-8"))}
    lines = json.loads((ROOT / "data/published/real_lines.json").read_text(encoding="utf-8"))["lines"]
    out["real_voice"] = [
        {
            "id": f"{sid}:{line}",
            "text": a["main"]["text_in"],
            "alt": a["base"]["text"],
            "ctx": samples[sid]["context"],
            "truth": _truth(samples[sid]["entities"]),
        }
        for line, rows in lines.items()
        for sid, a in rows.items()
    ]
    return out


def _number(kind: str, value) -> str:
    text = str(value)
    if kind == "AMOUNT":
        cleaned = re.sub(r"[^\d.]", "", text)
        try:
            return f"{float(cleaned):.2f}"
        except ValueError:
            return ""
    digits = re.sub(r"\D", "", text)
    return digits[-10:] if kind == "PHONE" and len(digits) > 10 and digits.startswith(("91", "0")) else digits


def _name(value) -> str:
    return re.sub(r"[^a-z0-9]", "", to_latin(str(value)).lower())


def _same(kind: str, want, got) -> bool:
    if kind in NUMBERS:
        return _number(kind, want) == _number(kind, got)
    a, b = _name(want), _name(got)
    return bool(b) and (a == b or a in b or (b in a and len(b) >= 0.7 * len(a)) or key(str(want)) == key(str(got)))


def _is(kind: str, bad, got) -> bool:
    return _number(kind, bad) == _number(kind, got) if kind in NUMBERS else _name(bad) in _name(got)


def score(case: dict, out: dict) -> dict:
    """solved: every fact right and nothing false. unsafe: something false was stated with no question."""
    said = [f for f in out["facts"] if not f["ask"]]
    asked = [f for f in out["facts"] if f["ask"]]
    rights = [t for t in case["truth"] if t[0] == "right"]
    tally: collections.Counter = collections.Counter()
    for mode, kind, value in case["truth"]:
        typed = [f for f in said if f["type"] == kind]
        questioned = any(f["type"] == kind for f in asked)
        if mode == "right":
            in_text = kind not in NUMBERS and _name(value) in _name(out["text"])
            if in_text or any(_same(kind, value, f["value"]) for f in typed):
                tally["right"] += 1
            elif questioned:
                tally["asked"] += 1
            elif any(not any(_same(kind, r[2], f["value"]) for r in rights if r[1] == kind) for f in typed):
                tally["wrong"] += 1
            else:
                tally["missed"] += 1
        elif mode == "ask":
            tally["right" if questioned else "wrong" if typed else "missed"] += 1
        elif mode == "forbid":
            rewritten = (
                kind not in NUMBERS and _name(value) in _name(out["text"]) and _name(value) not in _name(case["text"])
            )
            tally["false" if rewritten or any(_is(kind, value, f["value"]) for f in typed) else "clean"] += 1
        else:
            tally["false" if typed else "needless_question" if questioned else "clean"] += 1
    unsafe = tally["wrong"] + tally["false"] > 0
    solved = not unsafe and not (tally["asked"] + tally["missed"] + tally["needless_question"])
    return {"state": "unsafe" if unsafe else "solved" if solved else "unsolved", "tally": dict(tally)}


def _one(case: dict, label: str = "baseline") -> dict:
    from pehchaan_sdk import CustomTranscriptProvider, Pehchaan
    from pehchaan_sdk.meaning import MeaningReader
    from pehchaan_sdk.referee import MeaningReferee

    reader = (MeaningReferee if label == "candidate" else MeaningReader)(client())
    with tempfile.TemporaryDirectory() as folder:
        sdk = Pehchaan(
            CustomTranscriptProvider(),
            judge=OpenAIJudge(),
            memory=JsonMemoryStore(folder),
            meaning=reader,
        )
        result = sdk.verify_transcript(case["text"], case["ctx"], case.get("alt"))
    return {
        "facts": [{"type": f.type, "value": f.value, "ask": f.status == "FLAGGED"} for f in result.entities],
        "text": result.verified_text,
        "ms": result.telemetry.harness_ms,
    }


def run(label: str) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    file = RUNS / f"{label}.json"
    if file.exists():
        raise SystemExit(f"{file.name} already exists. Each gate run happens once.")
    sets = load_sets()
    with ThreadPoolExecutor(6) as pool:
        answers = {
            name: dict(zip([c["id"] for c in cases], pool.map(lambda c: _one(c, label), cases), strict=True))
            for name, cases in sets.items()
        }
    file.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
    print(f"saved {label}: {sum(len(v) for v in answers.values())} answers")


def summary(cases: list[dict], answers: dict) -> dict:
    states = collections.Counter(score(c, answers[c["id"]])["state"] for c in cases)
    times = sorted(answers[c["id"]]["ms"] for c in cases)
    return {
        "calls": len(cases),
        "solved": states["solved"],
        "unsafe": states["unsafe"],
        "unsolved": states["unsolved"],
        "median_ms": round(times[len(times) // 2]),
    }


def verdict() -> dict:
    sets = load_sets()
    old, new = (json.loads((RUNS / f"{x}.json").read_text(encoding="utf-8")) for x in ("baseline", "candidate"))
    table = {
        name: {"baseline": summary(c, old[name]), "with_meaning": summary(c, new[name])} for name, c in sets.items()
    }
    recorded_ok = all(
        table[n]["with_meaning"]["unsafe"] <= table[n]["baseline"]["unsafe"]
        and table[n]["with_meaning"]["solved"] >= table[n]["baseline"]["solved"]
        for n in RECORDED
    )
    fresh = table["fresh_attacks"]
    halved = fresh["with_meaning"]["unsafe"] * 2 <= fresh["baseline"]["unsafe"]
    return {
        "passed": recorded_ok and halved,
        "recorded_no_worse": recorded_ok,
        "fresh_unsafe_halved": halved,
        "table": table,
    }


if __name__ == "__main__":
    if sys.argv[1:2] == ["run"]:
        run(sys.argv[2])
    else:
        print(json.dumps(verdict(), indent=1))
