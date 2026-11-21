"""The benchmark must be honest: exact labels, clean dev/test split, locked test set, working runner."""
import hashlib
import json
import sys

from bench.score import entity_correct
from pehchaan.config import path, settings


def _load(split):
    return [json.loads(x) for x in (path("bench") / f"{split}_scripts.jsonl").read_text(encoding="utf-8").splitlines()]


def test_test_set_is_locked():
    digest = hashlib.sha256((path("bench") / "test_scripts.jsonl").read_bytes()).hexdigest()
    assert (path("bench") / "test_scripts.sha256").read_text().strip() == digest


def test_real_voice_test_set_uses_only_languages_the_recorder_speaks():
    assert {s["lang"] for s in _load("test")} <= {"hi", "hl", "en"}


def test_dev_and_test_share_no_people_or_places():
    def names(split):
        return {e["value"] for s in _load(split) for e in s["entities"] if e["type"] in ("PERSON", "PLACE")}
    assert names("dev").isdisjoint(names("test"))


def test_scorer_accepts_every_reference_transcript():
    for split in ("dev", "test"):
        for s in _load(split):
            for e in s["entities"]:
                assert entity_correct(e, s["reference"]), (s["script_id"], e)


def test_simulated_run_writes_a_report(tmp_path, monkeypatch):
    from bench import run
    monkeypatch.setitem(settings()["paths"], "results", str(tmp_path))
    monkeypatch.setitem(settings()["bench"], "bootstrap_iters", 30)
    monkeypatch.setattr(sys, "argv", ["run", "--clips", "dev", "--simulate", "--limit", "4",
                                      "--systems", "B0_asr_plain,P_C3"])
    run.main()
    summary = json.loads((tmp_path / "latest_dev_SIM.json").read_text())
    assert summary["simulated"] and set(summary["systems"]) == {"B0_asr_plain", "P_C3"}
