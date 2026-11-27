"""Check paired provider input parity and pinning without live credentials."""

import hashlib
import json

from bench.live.speech import collect


def test_paired_speech_uses_identical_pinned_audio_and_hints(tmp_path, monkeypatch):
    audio = tmp_path / "invented.wav"
    audio.write_bytes(b"same audio bytes for both adapters")
    manifest = tmp_path / "paired.jsonl"
    manifest.write_text(json.dumps({
        "id": "clip-1", "audio": audio.name, "sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
        "dataset": "synthetic-unit-test", "revision": "v1", "license": "fixture",
        "processing_ref": "invented", "speaker": "synthetic", "language": "en", "condition": "simulated_phone",
        "transcript": "Order ID AC725.", "facts": ["AC725"], "hints": ["Order ID"],
    }) + "\n")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-for-test")
    monkeypatch.setenv("SARVAM_API_KEY", "fake-for-test")
    requests = []

    def provider(name):
        def transcribe(path, clip, hints):
            requests.append((name, path.read_bytes(), hints))
            return clip.transcript

        return transcribe

    monkeypatch.setattr("bench.live.speech._openai", provider("openai"))
    monkeypatch.setattr("bench.live.speech._sarvam", provider("sarvam"))
    report = collect(manifest, ["openai", "sarvam"], 1)
    assert requests[0][1:] == requests[2][1:]
    assert requests[1][1:] == requests[3][1:]
    assert len(report["records"]) == 4
    assert {row["model"] for row in report["records"]} == {"gpt-transcribe", "saaras:v4"}
    assert all(row["word_error_rate"] == 0 and row["exact_facts"] == 1 for row in report["records"])


def test_provider_replay_pairs_hashes_and_scores_the_provider_words():
    import pytest

    from bench.live.dataset import load_split
    from bench.live.provider_replay import paired_replays

    rows, _ = load_split("dev")
    row = rows[0]
    captured = [
        {"opportunity_id": row.id, "track": "plain", "line": "clean", "turn_stage": stage, "audio_sha256": stage,
         "provider": provider, "model": f"model-{provider}", "transcript": transcript}
        for provider in ("openai", "sarvam")
        for stage, transcript in (("initial", row.transcript), ("readback", row.reply))
    ]
    captured[-1]["transcript"] = "yes"
    report = paired_replays([row], captured)["paired_opportunity_reports"]["plain/clean"]
    assert report["openai"]["systems"]["calibrated"]["overall"]["correct_completion"] == 1
    assert report["sarvam"]["systems"]["calibrated"]["overall"]["correct_completion"] == 0
    captured[-1]["audio_sha256"] = "different-audio"
    with pytest.raises(ValueError, match="audio hashes differ"):
        paired_replays([row], captured)
