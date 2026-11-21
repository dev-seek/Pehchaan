"""
Ship what the public site needs in git: measured results and the model answers for every sample call.

  python tools/pack_demo.py     (after a real `make bench-dev`; a sample with no cached answer calls the API once)

With the answers packaged, sample calls cost nothing, survive a dead network on stage, and match what was measured.
Publishing then proves it: a separate locked public process replays every sample with an empty cache and no API key.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VERIFY_FLAG = "--verify-offline"
os.environ["PEHCHAAN_MODE"] = "public" if VERIFY_FLAG in sys.argv else "local"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.server import app  # noqa: E402
from pehchaan import openai_client  # noqa: E402
from pehchaan.config import ROOT, settings  # noqa: E402


def publish_results() -> None:
    """Aggregates only. Per-clip exam output stays in results/, which is not in git."""
    for name in ("dev", *settings()["exam"]["conditions"]):
        latest = ROOT / settings()["paths"]["results"] / f"latest_{name}.json"
        if not latest.exists():
            continue
        report = json.loads(latest.read_text(encoding="utf-8"))
        if report.get("simulated"):
            raise SystemExit("Refusing to publish a simulated run.")
        report.pop("dir", None)
        target = ROOT / "data" / "published" / f"benchmark_{name}.json"
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


def verify_offline() -> None:
    """Runs in the locked public mode: every sample must finish from packaged answers alone."""
    with tempfile.TemporaryDirectory() as empty_cache:
        settings()["paths"]["cache"] = empty_cache
        client = TestClient(app)
        presets = client.get("/api/demo/presets").json()
        for preset in presets:
            reply = client.post("/api/demo/compare", data={"preset": preset["id"]})
            events = [json.loads(line) for line in reply.text.splitlines() if line.strip()]
            failed = [e["system_id"] for e in events if e["event"] == "system_error"]
            finished = sum(e["event"] == "result" for e in events)
            if reply.status_code != 200 or failed or not finished:
                raise SystemExit(f"{preset['id']} does not work offline: HTTP {reply.status_code}, failed {failed}")
    print(f"verified {len(presets)} sample calls offline in public mode")


def run_offline_check() -> None:
    env = {k: v for k, v in os.environ.items() if k != "PEHCHAAN_DEMO_PASSCODE"}
    env["OPENAI_API_KEY"] = "offline-check"
    subprocess.run([sys.executable, __file__, VERIFY_FLAG], check=True, env=env, cwd=ROOT)


if __name__ == "__main__":
    if VERIFY_FLAG in sys.argv:
        verify_offline()
    else:
        publish_results()
        pack_samples()
        run_offline_check()
