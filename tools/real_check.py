"""
Run the real-voice samples two ways, clean and through a simulated phone line, and publish the counts.

  python tools/real_check.py     (uses the API once per new audio; answers are cached)

These clips are one speaker and six calls, and they have been used to find bugs, so they are a check and not the exam.
The originals are only read. Phone copies are written beside them.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["PEHCHAAN_MODE"] = "local"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.demo_presets import real_samples  # noqa: E402
from app.server import app  # noqa: E402
from pehchaan.config import ROOT, settings  # noqa: E402
from tools.make_audio import degrade  # noqa: E402

OUTPUT = ROOT / "data" / "published" / "real_voice.json"


def recorded() -> list[dict]:
    return [s for s in real_samples() if (ROOT / s["audio"]).is_file()]


def line_versions(samples: list[dict], name: str, changes: dict) -> list[dict]:
    folder = ROOT / "data" / "demo" / "audio" / f"real_{name}"
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for sample in samples:
        target = folder / f"{sample['id']}.wav"
        if not target.exists():
            degrade(ROOT / sample["audio"], target, **changes)
        out.append({**sample, "audio": str(target.relative_to(ROOT))})
    return out


def run_sample(client: TestClient, sample_id: str) -> dict[str, dict]:
    reply = client.post("/api/demo/compare", data={"preset": sample_id})
    events = [json.loads(line) for line in reply.text.splitlines() if line.strip()]
    failed = [e["system_id"] for e in events if e["event"] == "system_error"]
    if reply.status_code != 200 or failed:
        raise SystemExit(f"{sample_id} failed: HTTP {reply.status_code}, {failed}")
    return {e["system_id"]: e["result"] for e in events if e["event"] == "result"}


def add_clip(totals: dict[str, dict], results: dict[str, dict]) -> None:
    for system, result in results.items():
        scored = result.get("scored")
        if not scored:
            continue
        row = totals.setdefault(system, {"facts": 0, "right": 0, "silent": 0, "asked": 0})
        row["facts"] += len(scored["entities"])
        row["right"] += sum(bool(f.get("correct")) for f in scored["entities"])
        row["silent"] += len(scored["silent_errors"])
        row["asked"] += sum(e["status"] == "FLAGGED" for e in result.get("entities", []))


def measure(client: TestClient, samples: list[dict]) -> dict:
    totals: dict[str, dict] = {}
    clips = {}
    for sample in samples:
        results = run_sample(client, sample["id"])
        add_clip(totals, results)
        clips[sample["id"]] = {
            system: result["scored"]["silent_errors"] for system, result in results.items() if result.get("scored")
        }
    return {"totals": totals, "silent_by_clip": clips}


def main() -> None:
    clean = recorded()
    if not clean:
        raise SystemExit("No real-voice recordings found. Record them at /studio first.")
    client = TestClient(app)
    report = {
        "label": f"{len(clean)} real-voice clips, one speaker. Used to find bugs, so this is a check and not the exam.",
        "clips": len(clean),
        "clean": measure(client, clean),
    }
    conditions = settings()["real_check"]["conditions"]
    with tempfile.TemporaryDirectory() as folder:
        for name, changes in conditions.items():
            catalog = Path(folder) / f"{name}.json"
            versions = line_versions(clean, name, changes or {})
            catalog.write_text(json.dumps(versions, ensure_ascii=False), encoding="utf-8")
            settings()["demo"]["real_samples"] = str(catalog)
            report[name] = measure(client, versions)
    OUTPUT.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    for condition in ("clean", *conditions):
        print(condition)
        for system in settings()["real_check"]["show"]:
            row = report[condition]["totals"][system]
            print(f"  {system:22} right {row['right']}/{row['facts']}  silent {row['silent']}  asked {row['asked']}")


if __name__ == "__main__":
    main()
