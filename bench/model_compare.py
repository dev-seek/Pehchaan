"""
The same frozen harness on different speech models. Run: `make model-compare`.

Each model transcribes the same audio with no keywords, because not every model accepts them. Pehchaan then runs on
that transcript with normal and with misleading context, and the independent scorer marks every fact.
Only dev clips and the six real-voice samples are used. The locked exam clips never enter this comparison.
"""

from __future__ import annotations

import json
import statistics
from concurrent.futures import ThreadPoolExecutor

from pehchaan.config import ROOT, path, settings

from .run import load_jsonl
from .score import aggregate, bootstrap_ci, score_clip
from .systems import AsrRequest, context_at, execute_system

OUTPUT = ROOT / "data" / "published" / "model_compare.json"
SYSTEMS = {
    "plain": {"kind": "asr"},
    "C3": {"kind": "pehchaan", "level": "C3"},
    "C4": {"kind": "pehchaan", "level": "C4"},
}


def dev_calls() -> list[dict]:
    scripts = {s["script_id"]: s for s in load_jsonl(path("bench") / "dev_scripts.jsonl")}
    return [
        {"id": c["clip_id"], "audio": ROOT / c["audio"], "script": scripts[c["script_id"]]}
        for c in load_jsonl(path("bench") / "dev_clips.jsonl")
    ]


def real_line_calls() -> list[dict]:
    samples = json.loads((ROOT / settings()["demo"]["real_samples"]).read_text(encoding="utf-8"))
    calls = []
    for line in settings()["model_compare"]["real_lines"]:
        for sample in samples:
            audio = ROOT / "data" / "demo" / "audio" / f"real_{line}" / f"{sample['id']}.wav"
            if not audio.is_file():
                raise SystemExit(f"{audio.name} is missing for line '{line}'. Run: make real-check")
            calls.append({"id": f"{sample['id']}__{line}", "audio": audio, "script": {"lang": "real", **sample}})
    return calls


def _transcribe_all(model: str, calls: list[dict]) -> dict[str, dict]:
    request = AsrRequest(model, (), False)
    with ThreadPoolExecutor(max_workers=settings()["asr"]["max_workers"]) as pool:
        answers = pool.map(lambda call: request.run(call["audio"]), calls)
        return {call["id"]: answer for call, answer in zip(calls, answers, strict=True)}


def _second_opinion_model(model: str) -> str:
    cfg = settings()["model_compare"]["second_opinion"]
    return cfg["when_same"] if model == cfg["default"] else cfg["default"]


def _score(call: dict, name: str, transcript: dict, second: dict) -> dict:
    script = call["script"]
    system = SYSTEMS[name]
    ctx = context_at(script, system.get("level", "C0"))
    output = execute_system(system, {"text": transcript["text"], "tokens": []}, ctx, second_opinion=second)
    row = score_clip(
        script["entities"],
        script["reference"],
        output["text"],
        output.get("in_text"),
        output.get("flags"),
        output["known"],
    )
    row.update(
        clip_id=call["id"],
        system=name,
        lang=script["lang"],
        harness_ms=output.get("harness_ms"),
        llm_calls=output.get("llm_calls", 0),
        text=output["text"],
        in_text=output.get("in_text"),
        reference=script["reference"],
        asr_ms=transcript.get("latency_ms"),
    )
    return row


def _metrics(rows: list[dict]) -> dict:
    cfg = settings()["bench"]
    summary = aggregate(rows)
    return {
        "facts": summary["entities"],
        "accuracy": summary["entity_accuracy"],
        "silent": summary["silent_error_rate"],
        "accuracy_ci": bootstrap_ci(rows, "entity_accuracy", cfg["bootstrap_iters"], cfg["seed"]),
        "silent_ci": bootstrap_ci(rows, "silent_error_rate", cfg["bootstrap_iters"], cfg["seed"]),
        "damaged": summary.get("damaged_edits", 0),
        "flags_per_clip": summary.get("flags_per_clip", 0),
    }


def measure(model: str, calls: list[dict]) -> dict:
    transcripts = _transcribe_all(model, calls)
    seconds = _transcribe_all(_second_opinion_model(model), calls)
    result = {
        "second_opinion": _second_opinion_model(model),
        "asr_ms_p50": statistics.median(t["latency_ms"] for t in transcripts.values()),
    }
    for name in SYSTEMS:
        result[name] = _metrics([_score(c, name, transcripts[c["id"]], seconds[c["id"]]) for c in calls])
    return result


def main() -> None:
    cfg = settings()["model_compare"]
    report = {"note": cfg["note"], "datasets": {}}
    for name, calls, label in (
        ("dev", dev_calls(), "60 development calls, synthetic voices, used for tuning"),
        (
            "real_bad_lines",
            real_line_calls(),
            "6 real-voice calls, one speaker, on noisy, very noisy and dropping lines",
        ),
    ):
        models = {model: measure(model, calls) for model in cfg["models"]}
        report["datasets"][name] = {"label": label, "clips": len(calls), "models": models}
        print(label)
        for model, row in models.items():
            line = "  ".join(f"{k} {row[k]['accuracy'] * 100:.1f}/{row[k]['silent'] * 100:.1f}" for k in SYSTEMS)
            print(
                f"  {model:24} right/silent %: {line}  damaged {row['C3']['damaged']}/{row['C4']['damaged']}  "
                f"asr p50 {row['asr_ms_p50']:.0f} ms"
            )
    OUTPUT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
