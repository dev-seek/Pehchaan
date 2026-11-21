"""
Does learning actually help? Measured on calls the learner never saw.

  python -m bench.learning_proof     (needs a real dev run; makes no API calls; writes data/published/learning_dev.json)

Each dev script is spoken by two voices. A scripted user corrects the wrong names on voice A only, every correction goes
through the real learning gate (replayed on voice A only), then we score voice B before and after. Then the voices swap.
The script also tries a wrong answer for each correction, to measure how often the gate blocks a bad confirmation.
"""
from __future__ import annotations

import json
import random
from difflib import SequenceMatcher

from pehchaan.config import ROOT, settings

from .learning import Candidate, evaluate, replay
from .oracle import fact_correct, same_name
from .oracle.names import phon
from .oracle.numbers import segment

NAME_TYPES = ("PERSON", "ORG", "PLACE")
SYSTEMS = {"P_C0": ("C0", False), "P_C2": ("C2", False), "P_on_B1_C3": ("C3", True)}


def _sound(unit) -> str:
    return unit.key if unit.is_number else (phon(unit.surface)[0] or unit.key)


def heard_span(truth: str, reference: str, output: str) -> str | None:
    """The words in `output` standing where `reference` says `truth`."""
    ref, out = segment(reference), segment(output)
    words = len(truth.split())
    found = next(((i, i + w) for w in range(max(1, words - 1), words + 3) for i in range(len(ref) - w + 1)
                  if same_name(" ".join(u.surface for u in ref[i:i + w]), truth)), None)
    if found is None:
        return None
    low, high = 0, len(out)
    for block in SequenceMatcher(None, [_sound(u) for u in ref], [_sound(u) for u in out], autojunk=False).get_matching_blocks():
        if block.size and block.a + block.size <= found[0]:
            low = block.b + block.size
        elif block.size and block.a >= found[1]:
            high = block.b
            break
    span = out[low:high]
    if not span or len(span) > words + 2 or any(u.is_number for u in span):
        return None
    return " ".join(u.surface for u in span)


def _clips(system: str, level: str, needs_second: bool, rows: list[dict], scripts: dict) -> dict[str, list[dict]]:
    plain = {r["clip_id"]: r["text"] for r in rows if r["system"] == "B0_asr_plain"}
    voices: dict[str, list[dict]] = {}
    for r in (x for x in rows if x["system"] == system):
        script = scripts[r["clip_id"].split("__")[0]]
        voices.setdefault(r["clip_id"].rsplit("_", 1)[1], []).append({
            "clip_id": r["clip_id"], "text": r["in_text"], "level": level, "reference": script["reference"],
            "second_opinion": plain[r["clip_id"]] if needs_second else None,
            "context": script["context"], "entities": script["entities"]})
    return voices


def _score(clips: list[dict], memory: list[dict]) -> tuple[int, int, int, dict]:
    right = silent = total = 0
    state = {}
    for clip in clips:
        result, _ = replay(clip, memory)
        flagged = {e.etype.value for e in result.entities if e.status.value == "FLAGGED"}
        for fact in clip["entities"]:
            ok = fact_correct(fact, result.text_out)
            total += 1
            right += ok
            silent += not ok and fact["type"] not in flagged
            state[(clip["clip_id"], fact["type"], str(fact["value"]))] = ok
    return right, silent, total, state


def _fold(train: list[dict], test: list[dict], names: list[str], rng: random.Random) -> dict:
    memory: list[dict] = []
    tried = blocked = wrong_tried = wrong_blocked = 0
    for clip in train:
        output = replay(clip, memory)[0].text_out
        for fact in (f for f in clip["entities"] if f["type"] in NAME_TYPES and not fact_correct(f, output)):
            heard = heard_span(str(fact["value"]), clip["reference"], output)
            if not heard:
                continue
            wrong = rng.choice([n for n in names if not same_name(n, str(fact["value"]))])
            wrong_tried += 1
            wrong_blocked += not evaluate(Candidate(heard, wrong, fact["type"]), memory, train)["adopted"]
            tried += 1
            good = Candidate(heard, str(fact["value"]), fact["type"])
            if evaluate(good, memory, train)["adopted"]:
                memory.append(good.entry())
            else:
                blocked += 1
    before, after = _score(test, []), _score(test, memory)
    harmed = sum(was and not after[3][fact] for fact, was in before[3].items())
    return {"facts": before[2], "right_before": before[0], "right_after": after[0], "silent_before": before[1],
            "silent_after": after[1], "facts_harmed": harmed, "learned": len(memory), "true_fixes_not_adopted": blocked,
            "true_fixes_tried": tried, "wrong_tried": wrong_tried, "wrong_blocked": wrong_blocked}


def measure() -> dict:
    latest = json.loads((ROOT / settings()["paths"]["results"] / "latest_dev.json").read_text(encoding="utf-8"))
    if latest.get("simulated"):
        raise SystemExit("Refusing: the latest run is simulated.")
    rows = [json.loads(x) for x in (ROOT / latest["dir"] / "per_clip.jsonl").read_text(encoding="utf-8").splitlines() if x]
    lines = (ROOT / settings()["paths"]["bench"] / "dev_scripts.jsonl").read_text(encoding="utf-8").splitlines()
    scripts = {s["script_id"]: s for s in map(json.loads, filter(None, lines))}
    names = sorted({str(e["value"]) for s in scripts.values() for e in s["entities"] if e["type"] in NAME_TYPES})
    out: dict = {"run": latest["ran_at"], "clips": latest["n_clips"], "note": "dev only, synthetic voices, scripted user",
                 "systems": {}}
    for sid, (level, second) in SYSTEMS.items():
        voices = _clips(sid, level, second, rows, scripts)
        first, other = sorted(voices)
        rng = random.Random(settings()["bench"]["seed"])
        folds = [_fold(voices[first], voices[other], names, rng), _fold(voices[other], voices[first], names, rng)]
        out["systems"][sid] = {k: sum(f[k] for f in folds) for k in folds[0]}
    return out


if __name__ == "__main__":
    result = measure()
    target = ROOT / "data" / "published" / "learning_dev.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    for sid, s in result["systems"].items():
        print(f"{sid}: right {s['right_before']}->{s['right_after']} of {s['facts']}, silent {s['silent_before']}->"
              f"{s['silent_after']}, harmed {s['facts_harmed']}, learned {s['learned']}/{s['true_fixes_tried']}, "
              f"wrong answers blocked {s['wrong_blocked']}/{s['wrong_tried']}")
