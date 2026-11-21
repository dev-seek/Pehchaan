"""
Scoring. Same rules for every system (baselines and Pehchaan), so the comparison is fair.

An entity counts as CORRECT in a transcript when:
  PERSON / ORG / PLACE : some span of the output sounds the same as the true value
                         (phonetic distance <= SCORE_TOLERANCE, i.e. only pure spelling variants like
                          Kondapoor/Kondapur pass; any real mishearing fails). Applied identically to all systems.
  PHONE / PIN          : some number in the output has exactly the true digits (+91/0 prefixes ignored)
  AMOUNT               : some number in the output has exactly the true value
Over-correction : correct in the system's INPUT transcript, wrong in its OUTPUT.
Silent error    : wrong in the output AND not flagged for a clarifying question.  <- headline metric
"""
from __future__ import annotations

import random
import statistics

import jiwer

from pehchaan.languages import get_registry
from pehchaan.numbers import find_runs, rules
from pehchaan.sound import distance
from pehchaan.text import normalize, tokenize

SCORE_TOLERANCE = 0.06
NAME_TYPES = {"PERSON", "ORG", "PLACE"}
CRITICAL = {"PHONE", "AMOUNT", "PIN"}


def _number_values(text: str) -> tuple[set[str], set[float]]:
    digits, values = set(), set()
    for r in find_runs(tokenize(text), get_registry()):
        if r.digit_reading:
            digits.add(rules.strip_phone_prefix(r.digit_reading))
            digits.add(r.digit_reading)
        if r.value_reading is not None:
            values.add(r.value_reading)
    return digits, values


def entity_correct(ent: dict, text: str) -> bool:
    t, v = ent["type"], ent["value"]
    if t in NAME_TYPES:
        toks = [x.norm for x in tokenize(text)]
        n = len(normalize(v).split())
        for w in {max(1, n - 1), n, n + 1}:
            for s in range(0, max(0, len(toks) - w + 1)):
                if distance(" ".join(toks[s:s + w]), v) <= SCORE_TOLERANCE:
                    return True
        return False
    digits, values = _number_values(text)
    if t in ("PHONE", "PIN"):
        return v in digits
    if t == "AMOUNT":
        return float(v) in values or v in digits
    return False


def canonical_for_wer(text: str) -> str:
    """Normalise text and write every number as digits, so '14,500' == 'fourteen thousand five hundred'."""
    toks = tokenize(text)
    runs = find_runs(toks, get_registry())
    out, i = [], 0
    for r in runs:
        out += [t.norm for t in toks[i:r.start]]
        if r.has_multiplier and r.value_reading is not None:
            out.append(str(int(r.value_reading)))
        else:
            out.append(r.digit_reading)
        i = r.end
    out += [t.norm for t in toks[i:]]
    return " ".join(x for x in out if x)


def wer(ref: str, hyp: str) -> float:
    r, h = canonical_for_wer(ref), canonical_for_wer(hyp)
    if not r:
        return 0.0
    return jiwer.wer(r, h or "<empty>")


def score_clip(entities: list[dict], reference: str, out_text: str, in_text: str | None,
               flags: list[dict] | None) -> dict:
    flags = list(flags or [])
    per = []
    used_flags: set[int] = set()
    for e in entities:
        ok = entity_correct(e, out_text)
        ok_in = entity_correct(e, in_text) if in_text is not None else ok
        flagged = False
        if not ok:
            for i, f in enumerate(flags):
                if i not in used_flags and f["etype"] == e["type"]:
                    used_flags.add(i)
                    flagged = True
                    break
        per.append({"type": e["type"], "value": e["value"], "correct": ok, "correct_in": ok_in,
                    "flagged": flagged, "over_corrected": ok_in and not ok})
    return {"entities": per, "wer": wer(reference, out_text), "n_flags": len(flags),
            "flags_warranted": len(used_flags)}


def aggregate(clips: list[dict]) -> dict:
    ents = [e for c in clips for e in c["entities"]]
    n = len(ents)

    def rate(pred, pool=None):
        pool = ents if pool is None else pool
        return (sum(1 for e in pool if pred(e)) / len(pool)) if pool else None

    crit = [e for e in ents if e["type"] in CRITICAL]
    n_flags = sum(c["n_flags"] for c in clips)
    in_ok = [e for e in ents if e["correct_in"]]
    out = {
        "clips": len(clips), "entities": n,
        "entity_accuracy": rate(lambda e: e["correct"]),
        "silent_error_rate": rate(lambda e: not e["correct"] and not e["flagged"]),
        "critical_accuracy": rate(lambda e: e["correct"], crit),
        "over_correction_rate": rate(lambda e: e["over_corrected"], in_ok),
        "flag_precision": (sum(c["flags_warranted"] for c in clips) / n_flags) if n_flags else None,
        "flags_per_clip": n_flags / len(clips) if clips else 0,
        "wer": statistics.mean(c["wer"] for c in clips) if clips else None,
        "by_type": {},
    }
    for t in sorted({e["type"] for e in ents}):
        pool = [e for e in ents if e["type"] == t]
        out["by_type"][t] = {"n": len(pool), "accuracy": rate(lambda e: e["correct"], pool)}
    reach = [e for e in ents if e.get("reachable")]
    unreach = [e for e in ents if e.get("reachable") is False]
    out["accuracy_reachable"] = rate(lambda e: e["correct"], reach) if reach else None
    out["accuracy_unreachable"] = rate(lambda e: e["correct"], unreach) if unreach else None
    lat = [c["harness_ms"] for c in clips if c.get("harness_ms") is not None]
    if lat:
        s = sorted(lat)
        out["harness_ms_p50"] = s[len(s) // 2]
        out["harness_ms_p95"] = s[min(len(s) - 1, int(len(s) * 0.95))]
    out["llm_calls_per_clip"] = statistics.mean(c.get("llm_calls", 0) for c in clips) if clips else 0
    out["by_lang"] = {}
    for lang in sorted({c.get("lang") for c in clips if c.get("lang")}):
        pool = [e for c in clips if c.get("lang") == lang for e in c["entities"]]
        out["by_lang"][lang] = {"n": len(pool), "accuracy": rate(lambda e: e["correct"], pool),
                                "silent_error_rate": rate(lambda e: not e["correct"] and not e["flagged"], pool)}
    return out


def bootstrap_ci(clips: list[dict], metric: str, iters: int, seed: int) -> tuple[float, float] | None:
    if not clips:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(iters):
        sample = [clips[rng.randrange(len(clips))] for _ in clips]
        v = aggregate(sample).get(metric)
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals)) - 1]
