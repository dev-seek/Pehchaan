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
from app.demo_results import serialize_result  # noqa: E402
from bench.systems import AsrRequest, context_at, execute_system  # noqa: E402
from pehchaan.config import ROOT, settings  # noqa: E402

OUTPUT = ROOT / "data" / "published" / "sample_models.json"


def one(preset: dict, audio: Path, model: str) -> dict:
    cfg = settings()
    profile = cfg["sdk"]["models"][model]
    contexts = {"context": preset.get("context", {}), "context_adv": preset.get("context_adv", {})}
    ctx = context_at(contexts, cfg["sdk"]["level"])
    keywords = tuple(ctx.keyword_list(cfg["asr"]["keywords_max"])) if profile["keywords"] else ()
    second_model = model if profile["keywords"] else cfg["sdk"]["second_opinion_model"]
    main = AsrRequest(model, keywords, False).run(audio)
    plain = AsrRequest(model, (), False).run(audio)
    second = AsrRequest(second_model, (), False).run(audio)
    truth = preset if "reference" in preset and "entities" in preset else None
    checked = execute_system({"kind": "pehchaan"}, main, ctx, second_opinion=second)
    base = execute_system({"kind": "asr"}, plain, ctx)
    return {"keywords_used": bool(keywords), "second_opinion_model": second_model,
            "base": serialize_result(base, ctx, plain, None, truth),
            "main": serialize_result(checked, ctx, main, second, truth)}


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
        json.dumps({"models": models, "samples": samples}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"packaged {len(models)} models on {len(samples)} sample calls -> {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
