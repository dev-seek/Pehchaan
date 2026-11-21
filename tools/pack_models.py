#!/usr/bin/env python3
"""
Package what each speech model did on each sample call, so the public model picker works with no API key.

Uses the measured setups: `gpt-transcribe` with keywords and a plain second opinion, other models with no keywords and
`gpt-transcribe` as second opinion. Answers come from the on-disk cache when present. Samples only, never exam clips.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("PEHCHAAN_MODE", "local")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.demo_presets import catalog, preset_audio  # noqa: E402
from bench.score import score_clip  # noqa: E402
from bench.systems import AsrRequest, context_at, known_names  # noqa: E402
from pehchaan import build_pipeline  # noqa: E402
from pehchaan.config import ROOT, settings  # noqa: E402
from pehchaan.judge import OpenAIJudge  # noqa: E402
from pehchaan.resolvers import NullMemoryStore  # noqa: E402
from pehchaan_sdk.client import build_result  # noqa: E402

OUTPUT = ROOT / "data" / "published" / "sample_models.json"


def _facts(preset: dict, text: str, flags: list[dict], in_text: str, known: list[str]) -> dict | None:
    if "reference" not in preset or "entities" not in preset:
        return None
    row = score_clip(preset["entities"], preset["reference"], text, in_text, flags, known)
    return {
        "total": len(row["entities"]),
        "right": sum(e["correct"] for e in row["entities"]),
        "silent": sum(not e["correct"] and not e["flagged"] for e in row["entities"]),
        "asked": sum(e["flagged"] for e in row["entities"]),
    }


def one(preset: dict, audio: Path, model: str) -> dict:
    cfg = settings()
    profile = cfg["sdk"]["models"][model]
    contexts = {"context": preset.get("context", {}), "context_adv": preset.get("context_adv", {})}
    ctx = context_at(contexts, cfg["sdk"]["level"])
    keywords = tuple(ctx.keyword_list(cfg["asr"]["keywords_max"])) if profile["keywords"] else ()
    second_model = model if profile["keywords"] else cfg["sdk"]["second_opinion_model"]
    main = AsrRequest(model, keywords, False).run(audio)
    plain = main if not keywords else AsrRequest(model, (), False).run(audio)
    second = AsrRequest(second_model, (), False).run(audio)
    engine = build_pipeline(judge=OpenAIJudge(), memory=NullMemoryStore()).run(main["text"], ctx, None, second["text"])
    result = build_result(
        engine,
        model=model,
        second_model=second_model,
        stt_ms=main.get("latency_ms", 0),
        judge=None,
        evidence=profile["evidence"],
    ).model_dump()
    flags = [
        {"etype": e.etype.value, "surface": e.surface, "value": e.value, "options": [c["text"] for c in e.candidates]}
        for e in engine.entities
        if e.status.value == "FLAGGED"
    ]
    known = known_names(ctx)
    return {
        "plain_text": plain["text"],
        "input_text": main["text"],
        "keywords_used": bool(keywords),
        "result": result,
        "scores": {
            "plain": _facts(preset, plain["text"], [], plain["text"], known),
            "pehchaan": _facts(preset, engine.text_out, flags, main["text"], known),
        },
    }


def main() -> None:
    models = list(settings()["sdk"]["models"])
    jobs = [
        (sid, preset, preset_audio(preset), model)
        for sid, preset in catalog().items()
        if preset_audio(preset)
        for model in models
    ]
    with ThreadPoolExecutor(max_workers=settings()["asr"]["max_workers"]) as pool:
        answers = list(pool.map(lambda job: one(job[1], job[2], job[3]), jobs))
    samples: dict[str, dict] = {}
    for (sid, _, _, model), answer in zip(jobs, answers, strict=True):
        samples.setdefault(sid, {})[model] = answer
    OUTPUT.write_text(
        json.dumps({"models": models, "samples": samples}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"packaged {len(models)} models on {len(samples)} sample calls -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
