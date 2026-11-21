#!/usr/bin/env python3
"""
Run Pehchaan-Bench.

  python -m bench.run --clips dev                 # TTS dev clips (data/bench/dev_clips.jsonl)
  python -m bench.run --clips test_real           # YOUR locked real recordings  <- the headline numbers
  python -m bench.run --clips dev --simulate      # no API at all: fake ASR errors, to test the plumbing
  python -m bench.run --clips dev --systems P_C3,B0_asr_plain   # subset

Every API answer is cached under .cache/, so re-running after a threshold change costs nothing.
Writes results/<clips>_<timestamp>/{report.md, summary.json, per_clip.jsonl} and results/latest_<clips>.json
(the demo UI's Bench tab reads the latter).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pehchaan import CallContext
from pehchaan.config import ROOT, path, settings
from pehchaan.numbers import rules

from .exam import check_exam_allowed, labels_readable, record_exam
from .manifest import run_manifest
from .oracle import same_name
from .report import report_md
from .score import aggregate, bootstrap_ci, score_clip
from .systems import asr_request, context_at, execute_system, needed_transcripts, ordered_systems, primary_key


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def run_asr(clip: dict, script: dict, transcript_key: str) -> dict:
    return asr_request(script, transcript_key).run(ROOT / clip["audio"])


# --- offline simulator (plumbing tests only; NEVER reported as a result) --------------------------
def simulate_asr(script: dict, seed: int) -> dict:
    rng = random.Random(f"{seed}-{script['script_id']}")
    text = script["reference"]
    for e in script["entities"]:
        v = e["value"]
        if e["type"] in ("PERSON", "PLACE", "ORG") and rng.random() < 0.6:
            w = v
            for a, b in (("sh", "s"), ("v", "w"), ("aa", "a"), ("ee", "i"), ("th", "t"), ("dh", "d"), ("ya", "ia")):
                if a in w.lower() and rng.random() < 0.6:
                    w = re.sub(a, b, w, count=1, flags=re.I)
            if " " not in w and len(w) > 7 and rng.random() < 0.5:
                w = w[: len(w) // 2] + " " + w[len(w) // 2 :].lower()
            text = text.replace(v, w)
        if e["type"] == "PHONE" and rng.random() < 0.4:
            i = rng.randrange(1, 9)
            text = text.replace(v, v[:i] + v[i] + v[i:])
        if e["type"] == "AMOUNT" and rng.random() < 0.4:
            alt = rules.teen_ty_digit_variants(v)
            if alt:
                text = text.replace(v, alt[0])
    toks = [{"token": t, "logprob": -1.5 if rng.random() < 0.3 else -0.01} for t in re.findall(r"\S+\s*", text)]
    return {"text": text, "tokens": toks, "latency_ms": 0, "cached": True, "model": "SIMULATED"}


# ------------------------------------------------------------------------------------------------
def reachable(ent: dict, script: dict) -> bool:
    ctx = CallContext.build(script["context"], "C3")
    t, v = ent["type"], ent["value"]
    if t in ("PERSON", "ORG", "PLACE"):
        return any(c.etype.value == t and same_name(c.output, v) for c in ctx.candidates)
    if t == "PHONE":
        return v in ctx.phones
    if t == "AMOUNT":
        return float(v) in ctx.amounts
    if t == "PIN":
        return v in ctx.pins
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True, help="dev | test_real | test_synth  (reads data/bench/<x>_clips.jsonl)")
    ap.add_argument("--systems", default=None, help="comma-separated system ids (default: all in settings)")
    ap.add_argument("--simulate", action="store_true", help="no API calls: fake ASR from the reference text")
    ap.add_argument("--no-verifier", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    cfg = settings()
    systems = cfg["bench"]["systems"]
    if a.systems:
        want = set(a.systems.split(","))
        keep = [s for s in systems if s["id"] in want]
        # pull in systems that the chosen ones read from
        for s in list(keep):
            on = s.get("input")
            if on and on not in {x["id"] for x in keep} and any(x["id"] == on for x in systems):
                keep.append(next(x for x in systems if x["id"] == on))
        systems = keep
    check_exam_allowed(a.clips, a.simulate, ROOT / cfg["paths"]["results"])
    split = a.clips.split("_")[0]
    scripts = {s["script_id"]: s for s in load_jsonl(path("bench") / f"{split}_scripts.jsonl")}
    if a.simulate:
        clips = [{"clip_id": f"{sid}__sim", "script_id": sid, "audio": None, "source": "SIMULATED"} for sid in scripts]
    else:
        clips = load_jsonl(path("bench") / f"{a.clips}_clips.jsonl")
    clips = clips[: a.limit] if a.limit else clips
    if split == "test" and not a.simulate:
        labels_readable(scripts.values())
    print(f"{len(clips)} clips, {len(systems)} systems{'  [SIMULATED ASR - plumbing test only]' if a.simulate else ''}")

    # 1. transcripts ------------------------------------------------------------------------------
    need = needed_transcripts(systems)
    tr: dict[str, dict[str, dict]] = {c["clip_id"]: {} for c in clips}
    if a.simulate:
        for c in clips:
            sim = simulate_asr(scripts[c["script_id"]], cfg["bench"]["seed"])
            for k in need:
                tr[c["clip_id"]][k] = sim if k == "asr_logprobs" else {**sim, "tokens": []}
    else:
        jobs = {}
        with ThreadPoolExecutor(max_workers=cfg["asr"]["max_workers"]) as ex:
            for c in clips:
                for k in need:
                    jobs[ex.submit(run_asr, c, scripts[c["script_id"]], k)] = (c["clip_id"], k)
            for i, fut in enumerate(as_completed(jobs), 1):
                cid, k = jobs[fut]
                try:
                    tr[cid][k] = fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"  ASR FAIL {cid} {k}: {e}")
                    tr[cid][k] = {"text": "", "tokens": [], "error": str(e)}
                if i % 20 == 0:
                    print(f"  asr {i}/{len(jobs)}")

    # 2. systems ----------------------------------------------------------------------------------
    by_id = {s["id"]: s for s in systems}
    outputs: dict[str, dict[str, dict]] = {c["clip_id"]: {} for c in clips}

    for c in clips:
        cid, sc = c["clip_id"], scripts[c["script_id"]]
        for s in ordered_systems(systems):
            key = primary_key(s, by_id)
            src = tr[cid].get(key)
            if src is None:
                src = {"text": outputs[cid][key]["text"], "tokens": []}
            ctx = context_at(sc, s.get("level", "C0"))
            second = tr[cid].get(s.get("second_opinion"))
            try:
                outputs[cid][s["id"]] = execute_system(
                    s, src, ctx, second_opinion=second, use_judge=not a.no_verifier, simulate=a.simulate
                )
            except Exception as e:  # noqa: BLE001 - retain untouched input when the rewrite baseline fails
                if s["kind"] != "naive_llm":
                    raise
                print(f"  naive LLM FAIL {cid}: {e}")
                outputs[cid][s["id"]] = execute_system(s, src, ctx, simulate=True)

    # 3. score ------------------------------------------------------------------------------------
    per_clip, by_sys = [], {s["id"]: [] for s in systems}
    for c in clips:
        sc = scripts[c["script_id"]]
        reach = {i: reachable(e, sc) for i, e in enumerate(sc["entities"])}
        for s in systems:
            o = outputs[c["clip_id"]][s["id"]]
            res = score_clip(sc["entities"], sc["reference"], o["text"], o.get("in_text"), o.get("flags"), o["known"])
            for i, e in enumerate(res["entities"]):
                e["reachable"] = reach[i]
            res.update(
                clip_id=c["clip_id"],
                system=s["id"],
                lang=sc["lang"],
                harness_ms=o.get("harness_ms"),
                llm_calls=o.get("llm_calls", 0),
                text=o["text"],
                in_text=o.get("in_text"),
                reference=sc["reference"],
            )
            asr_sources = [primary_key(s, by_id), s.get("second_opinion")]
            asr_times = [tr[c["clip_id"]].get(k, {}).get("latency_ms") for k in asr_sources if k]
            if not a.simulate and asr_times and all(ms is not None for ms in asr_times):
                res["asr_ms"] = max(asr_times)
            if "entities" in o:
                res["pehchaan_entities"] = o["entities"]
            by_sys[s["id"]].append(res)
            per_clip.append(res)

    iters, seed = cfg["bench"]["bootstrap_iters"], cfg["bench"]["seed"]
    summary = {
        "clips": a.clips,
        "simulated": a.simulate,
        "n_clips": len(clips),
        "ran_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "models": cfg["models"],
        "manifest": run_manifest(),
        "main_system": cfg["bench"]["main_system"],
        "systems": {},
    }
    for sid, rows in by_sys.items():
        agg = aggregate(rows)
        agg["ci95"] = {m: bootstrap_ci(rows, m, iters, seed) for m in ("entity_accuracy", "silent_error_rate")}
        summary["systems"][sid] = agg

    out_dir = (
        ROOT / cfg["paths"]["results"] / f"{a.clips}{'_SIM' if a.simulate else ''}_{time.strftime('%Y%m%d_%H%M%S')}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (out_dir / "per_clip.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in per_clip))
    md = report_md(summary)
    (out_dir / "report.md").write_text(md)
    latest = ROOT / cfg["paths"]["results"] / f"latest_{a.clips}{'_SIM' if a.simulate else ''}.json"
    shown_dir = out_dir.relative_to(ROOT) if out_dir.is_relative_to(ROOT) else out_dir
    latest.write_text(json.dumps({"dir": str(shown_dir), **summary}, indent=2, ensure_ascii=False))
    if a.clips == "test_real_phone" and not a.simulate:
        record_exam(ROOT / cfg["paths"]["results"], shown_dir, summary["manifest"])
    print(md)
    print(f"\nsaved -> {out_dir}")


if __name__ == "__main__":
    sys.exit(main())
