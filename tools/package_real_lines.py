"""
Package what each system did on the six real-voice samples at every phone-line quality, so Compare can show them for free.

  python tools/package_real_lines.py

It only replays saved answers. The API address is pointed at nothing, so a missing answer fails instead of spending credit.
The result must match data/published/real_voice.json exactly. These clips found bugs, so they are a check and not the exam.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.update(PEHCHAAN_MODE="local", OPENAI_API_KEY="sk-offline-replay", OPENAI_BASE_URL="http://127.0.0.1:9/v1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.server import app  # noqa: E402
from pehchaan.config import ROOT, settings  # noqa: E402
from tools.real_check import line_versions, recorded, run_sample  # noqa: E402

OUTPUT = ROOT / "data" / "published" / "real_lines.json"
PUBLISHED = ROOT / "data" / "published" / "real_voice.json"
SHOWN = {"base": "B0_asr_plain", "keywords": "B1_asr_keywords_C3", "main": "P_on_B1_C3"}


def compact(result: dict) -> dict:
    return {k: v for k, v in result.items() if k != "asr"}


def package(client: TestClient, samples: list[dict], expected: dict) -> dict:
    out = {}
    for sample in samples:
        results = run_sample(client, sample["id"])
        for system in SHOWN.values():
            if results[system]["scored"]["silent_errors"] != expected["silent_by_clip"][sample["id"]][system]:
                raise SystemExit(f"{sample['id']} {system} no longer matches the published check")
        out[sample["id"]] = {name: compact(results[system]) for name, system in SHOWN.items()}
    return out


def main() -> None:
    published = json.loads(PUBLISHED.read_text(encoding="utf-8"))
    clean = recorded()
    client = TestClient(app)
    report = {"label": published["label"], "lines": {"clean": package(client, clean, published["clean"])}}
    with tempfile.TemporaryDirectory() as folder:
        for name, changes in settings()["real_check"]["conditions"].items():
            catalog = Path(folder) / f"{name}.json"
            catalog.write_text(json.dumps(line_versions(clean, name, changes or {}), ensure_ascii=False), encoding="utf-8")
            settings()["demo"]["real_samples"] = str(catalog)
            report["lines"][name] = package(client, json.loads(catalog.read_text(encoding="utf-8")), published[name])
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}: {OUTPUT.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
