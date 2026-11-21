"""
Which packaged call shows each demo best? Runs every free sample once, offline, and records the answer.

    .venv/bin/python tools/demo_highlights.py      # writes data/published/demo_highlights.json

The site reads this file, so opening a tab never has to replay all the samples.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / "data" / "published" / "demo_highlights.json"
NUMBERS = {"PHONE", "PIN", "AMOUNT"}
MAIN = "P_on_B1_C3"
LEVELS = ("P_C0", "P_C2", MAIN, "P_on_B1_C4")


def _state(fact: dict) -> str:
    return "right" if fact["correct"] else "asked" if fact.get("flagged") else "silent"


def _silent(result: dict) -> int:
    return sum(_state(fact) == "silent" for fact in result["scored"]["entities"])


def _context_spread(results: dict) -> int:
    rows = [[_state(fact) for fact in results[system]["scored"]["entities"]] for system in LEVELS]
    return sum(len(set(states)) > 1 for states in zip(*rows, strict=True))


def _teaches(results: dict) -> bool:
    """A learnable question whose known answer differs from what was heard, so the replay visibly changes."""
    for system in (MAIN, "P_on_B1_C4"):
        result = results[system]
        for question in result["questions"]:
            entity = next(e for e in result["entities"] if e["id"] == question["entity_id"])
            known = [f["value"] for f in result["scored"]["entities"] if f["type"] == entity["etype"] and f.get("flagged")]
            if entity["etype"] not in NUMBERS and known and known[0] != entity["surface"]:
                return True
    return False


def _best(rows: list[dict], score) -> str | None:
    ranked = sorted(rows, key=lambda row: (-score(row["results"]), row["kind"] != "real", row["id"]))
    return ranked[0]["id"] if ranked and score(ranked[0]["results"]) > 0 else None


def compute(client) -> dict:
    rows = []
    for preset in client.get("/api/demo/presets").json():
        lines = client.post("/api/demo/compare", data={"preset": preset["id"]}).text.splitlines()
        events = [json.loads(line) for line in lines if line.strip()]
        results = {e["system_id"]: e["result"] for e in events if e["event"] == "result"}
        rows.append({"id": preset["id"], "kind": preset["kind"], "results": results})
    return {
        "context": _best(rows, _context_spread),
        "llm": _best(rows, lambda r: _silent(r["B2_naive_llm_C4"]) - _silent(r["P_on_B1_C4"])),
        "learning": _best(rows, lambda r: int(_teaches(r))),
    }


if __name__ == "__main__":
    os.environ["PEHCHAAN_MODE"] = "public"
    os.environ.pop("ENV", None)
    from fastapi.testclient import TestClient

    from app.server import app

    answer = compute(TestClient(app))
    OUTPUT.write_text(json.dumps(answer, indent=1) + "\n", encoding="utf-8")
    print(answer)
