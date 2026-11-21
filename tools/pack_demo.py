"""
Ship what the public site needs in git: measured results and the model answers for every sample call.

  python tools/pack_demo.py     (after a real `make bench-dev`; a sample with no cached answer calls the API once)

With the answers packaged, sample calls cost nothing, survive a dead network on stage, and match what was measured.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

os.environ["PEHCHAAN_MODE"] = "local"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.server import app  # noqa: E402
from pehchaan import openai_client  # noqa: E402
from pehchaan.config import ROOT, settings  # noqa: E402


def publish_results() -> None:
    latest = ROOT / settings()["paths"]["results"] / "latest_dev.json"
    report = json.loads(latest.read_text(encoding="utf-8"))
    if report.get("simulated"):
        raise SystemExit("Refusing to publish a simulated run.")
    report.pop("dir", None)
    target = ROOT / "data" / "published" / "benchmark_dev.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"published {target.relative_to(ROOT)}")


def pack_samples() -> None:
    client = TestClient(app)
    openai_client.cache_trace = set()
    presets = client.get("/api/demo/presets").json()
    for preset in presets:
        reply = client.post("/api/demo/compare", data={"preset": preset["id"]})
        events = [json.loads(line) for line in reply.text.splitlines() if line.strip()]
        failed = [e["system_id"] for e in events if e["event"] == "system_error"]
        if reply.status_code != 200 or failed:
            raise SystemExit(f"{preset['id']} failed: {reply.status_code} {failed}")
    store = ROOT / settings()["demo"]["packaged_answers"]
    for found in openai_client.cache_trace:
        target = store / found.parent.name / found.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if found.resolve() != target.resolve():
            shutil.copyfile(found, target)
    print(f"packaged {len(openai_client.cache_trace)} answers for {len(presets)} sample calls")
    openai_client.cache_trace = None


if __name__ == "__main__":
    publish_results()
    pack_samples()
