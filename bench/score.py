"""
Scoring. Same rules for every system (baselines and Pehchaan), so the comparison is fair.

Facts are judged by the clean-room oracle (bench/oracle), which shares no code or word tables with the engine:
an engine blind spot can therefore never hide itself by also blinding the scorer (DECISIONS D-020).

Correct fact     : the output states the labelled value (see bench.oracle.fact_correct).
Over-correction  : a fact correct in the system's INPUT transcript, wrong in its OUTPUT.
Damaged edit     : any change from input to output that invents an entity, changes a number, or rewrites words
                   into something else (bench.oracle.audit_edits). Counts harm to text that is not a labelled fact.
Silent error     : wrong in the output AND no question was asked about that fact.  <- headline metric
"""
from __future__ import annotations

import random
import statistics
from collections import Counter
from collections.abc import Iterable

import jiwer

from .oracle import audit_edits, fact_correct, flag_refers_to, loosely_same, same_name
from .oracle.names import phon
from .oracle.numbers import segment

NAME_TYPES = {"PERSON", "ORG", "PLACE"}
CRITICAL = {"PHONE", "AMOUNT", "PIN"}


def entity_correct(ent: dict, text: str) -> bool:
    return fact_correct(ent, text)


def canonical_for_wer(text: str) -> str:
    """Script-independent words, with every number as digits, so '14,500' == 'fourteen thousand five hundred'."""
    return " ".join(u.digits or u.key if u.is_number else (phon(u.surface)[0] or u.key) for u in segment(text))


def wer(ref: str, hyp: str) -> float:
    r, h = canonical_for_wer(ref), canonical_for_wer(hyp)
    if not r:
        return 0.0
    return jiwer.wer(r, h or "<empty>")


def flag_addresses(flag: dict, entity: dict, out_text: str = "", reference: str = "") -> bool:
    """A question earns credit only if it is about this fact: same type, and for names the same option or position."""
    if flag["etype"] != entity["type"]:
        return False
    if entity["type"] in CRITICAL:
        return True
    truth = str(entity["value"])
    if any(same_name(option, truth) for option in flag.get("options", [])):
        return True
    surface = flag.get("surface") or ""
    return bool(surface) and (loosely_same(surface, truth) or flag_refers_to(surface, out_text, reference, truth))


def score_clip(entities: list[dict], reference: str, out_text: str, in_text: str | None,
               flags: list[dict] | None, known_names: Iterable[str] = ()) -> dict:
    flags = list(flags or [])
    per = []
    used_flags: set[int] = set()
    for e in entities:
        ok = entity_correct(e, out_text)
        ok_in = entity_correct(e, in_text) if in_text is not None else ok
        flagged = False
        if not ok:
            for i, f in enumerate(flags):
                if i not in used_flags and flag_addresses(f, e, out_text, reference):
                    used_flags.add(i)
                    flagged = True
                    break
        per.append({"type": e["type"], "value": e["value"], "correct": ok, "correct_in": ok_in,
                    "flagged": flagged, "over_corrected": ok_in and not ok})
    edits = audit_edits(in_text, out_text, entities, known_names) if in_text not in (None, out_text) else []
    return {"entities": per, "wer": wer(reference, out_text), "n_flags": len(flags),
            "flags_warranted": len(used_flags), "edits": [x for x in edits if x["kind"] != "format"],
            "n_damage": sum(1 for x in edits if x["kind"] == "damage")}


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
        "damaged_edits": sum(c.get("n_damage", 0) for c in clips),
        "clips_with_damage": sum(1 for c in clips if c.get("n_damage", 0)),
        "damage_by_reason": dict(Counter(x["reason"] for c in clips for x in c.get("edits", [])
                                         if x["kind"] == "damage")),
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
