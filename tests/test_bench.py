"""The benchmark must be honest: exact labels, clean dev/test split, locked test set, working runner."""

import hashlib
import json
import sys

import pytest

from bench.score import aggregate, entity_correct
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


def test_scorer_accepts_every_dev_reference_transcript():
    # The locked test set is checked only by bench.exam.labels_readable, which reports a count and no content.
    for s in _load("dev"):
        for e in s["entities"]:
            assert entity_correct(e, s["reference"]), (s["script_id"], e)


def test_exam_refuses_clean_audio_and_a_second_run(tmp_path):
    from bench.exam import check_exam_allowed, record_exam

    with pytest.raises(SystemExit, match="phone-line copy"):
        check_exam_allowed("test_real", False, tmp_path)
    check_exam_allowed("test_real_phone", False, tmp_path)
    record_exam(tmp_path, "test_real_phone", "results/x", {"config": "abc"})
    with pytest.raises(SystemExit, match="already ran"):
        check_exam_allowed("test_real_phone", False, tmp_path)
    check_exam_allowed("test_real_noisy", False, tmp_path)         # each registered line runs once
    check_exam_allowed("dev", False, tmp_path)


def test_exam_conditions_cannot_change_after_the_first_run(tmp_path, monkeypatch):
    from bench.exam import check_exam_allowed, record_exam

    record_exam(tmp_path, "test_real_phone", "results/x", {})
    changed = {**settings()["exam"]["conditions"], "test_real_noisy": {"noise_amplitude": 0.01}}
    monkeypatch.setitem(settings()["exam"], "conditions", changed)
    with pytest.raises(SystemExit, match="changed"):
        check_exam_allowed("test_real_noisy", False, tmp_path)


def test_exam_refuses_a_partial_run_and_an_unregistered_line(tmp_path):
    from bench.exam import check_exam_allowed

    with pytest.raises(SystemExit, match="whole"):
        check_exam_allowed("test_real_phone", False, tmp_path, partial=True)
    with pytest.raises(SystemExit, match="phone-line copy"):
        check_exam_allowed("test_real_street", False, tmp_path)


def test_a_failed_api_call_does_not_burn_the_exam():
    from bench.exam import require_complete

    good = {"c": {"k": {"text": "ok"}}}, {"c": {"s": {"entities": [{"reason": "fine"}]}}}
    require_complete(*good)
    with pytest.raises(SystemExit, match="Nothing was scored"):
        require_complete({"c": {"k": {"text": "", "error": "timeout"}}}, good[1])
    with pytest.raises(SystemExit, match="Nothing was scored"):
        require_complete(good[0], {"c": {"s": {"failed": True}}})
    with pytest.raises(SystemExit, match="Nothing was scored"):
        require_complete(good[0], {"c": {"s": {"entities": [{"reason": "judge unavailable (Timeout): x"}]}}})


def test_the_exam_needs_committed_code():
    from bench.exam import require_frozen

    require_frozen({"git_dirty": False})
    with pytest.raises(SystemExit, match="uncommitted"):
        require_frozen({"git_dirty": True})


def test_frozen_parts_report_what_changed():
    from bench.manifest import frozen_changes, run_manifest

    now = run_manifest()
    assert frozen_changes(now, now) == []
    assert frozen_changes({**now, "engine": "other"}, now) == ["engine"]


def test_noisy_exam_line_is_the_noisy_profile_measured_before_it():
    assert settings()["exam"]["conditions"]["test_real_noisy"] == settings()["real_check"]["conditions"]["noisy"]


def test_flag_earns_credit_only_for_the_fact_it_asks_about():
    from bench.score import flag_addresses

    truth = {"type": "PLACE", "value": "Kondapur"}
    assert flag_addresses({"etype": "PLACE", "surface": "Kondapoor ya", "options": ["Kondapur", "Kothapur"]}, truth)
    assert not flag_addresses({"etype": "PLACE", "surface": "Secunderabad", "options": ["Secunderabad"]}, truth)
    assert not flag_addresses({"etype": "PERSON", "surface": "Kondapur", "options": ["Kondapur"]}, truth)


def test_fact_type_breakdown_distinguishes_flags_from_silent_errors():
    pairs = [("PIN", True, False), ("PIN", False, True), ("PHONE", False, False)]
    facts = [
        {"type": kind, "correct": correct, "correct_in": correct, "flagged": flagged, "over_corrected": False}
        for kind, correct, flagged in pairs
    ]
    report = aggregate([{"entities": facts, "n_flags": 1, "flags_warranted": 1, "wer": 0.0}])
    assert report["by_type"] == {
        "PIN": {"n": 2, "accuracy": 0.5, "silent_error_rate": 0.0},
        "PHONE": {"n": 1, "accuracy": 0.0, "silent_error_rate": 1.0},
    }


def test_simulated_run_writes_a_report(tmp_path, monkeypatch):
    from bench import run

    monkeypatch.setitem(settings()["paths"], "results", str(tmp_path))
    monkeypatch.setitem(settings()["bench"], "bootstrap_iters", 30)
    monkeypatch.setattr(
        sys, "argv", ["run", "--clips", "dev", "--simulate", "--limit", "4", "--systems", "B0_asr_plain,P_C3"]
    )
    run.main()
    summary = json.loads((tmp_path / "latest_dev_SIM.json").read_text())
    assert summary["simulated"] and set(summary["systems"]) == {"B0_asr_plain", "P_C3"}


def _gate_state(silent=0.01, damaged=0, state="correct"):
    return {
        "n_clips": 1,
        "systems": {
            "P": {
                "silent_error_rate": silent,
                "over_correction_rate": 0.0,
                "damaged_edits": damaged,
                "flags_per_clip": 0.1,
                "facts": {"clip|PHONE|9": state},
            }
        },
    }


def test_gate_passes_an_equal_run_and_rejects_each_kind_of_regression():
    from bench.gate import compare

    assert compare(_gate_state(), _gate_state(), 0.05) == []
    assert any("silent_error_rate" in p for p in compare(_gate_state(), _gate_state(silent=0.02), 0.05))
    assert any("damaged_edits" in p for p in compare(_gate_state(), _gate_state(damaged=1), 0.05))
    assert any("now silently wrong" in p for p in compare(_gate_state(), _gate_state(state="silent"), 0.05))
