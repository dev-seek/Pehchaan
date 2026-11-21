"""Exercise the streaming comparison and replay with fake model responses."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import demo_api
from app.demo_state import DemoMemory, DemoRuns
from app.server import app
from bench import systems
from pehchaan.config import settings

MAIN = "P_on_B1_C3"
TEXT = "🙂 main Venkat bol raha hoon. Callback number 984801234."


def compare(client, *, data=None, files=None) -> tuple[dict, dict[str, dict]]:
    reply = client.post("/api/demo/compare", data=data, files=files)
    assert reply.status_code == 200
    assert reply.headers["content-type"] == "application/x-ndjson"
    messages = [json.loads(line) for line in reply.text.splitlines()]
    first, last = messages[0], messages[-1]
    assert first["event"] == "started"
    assert last == {"event": "done", "run_id": first["run_id"]}
    rest = {m["system_id"]: m for m in messages[1:-1]}
    assert len(rest) == len(messages) - 2 == len(first["systems"])
    return first, rest


@pytest.fixture
def demo_client(monkeypatch, tmp_path):
    monkeypatch.setattr(demo_api, "_runs", DemoRuns())
    monkeypatch.setattr(demo_api, "_memory", DemoMemory(tmp_path / "demo.sqlite3"))
    monkeypatch.setitem(settings()["verifier"], "enabled", False)
    monkeypatch.setitem(settings()["paths"], "cache", str(tmp_path))
    monkeypatch.setattr(systems, "naive_fix",
                        lambda text, ctx, **kwargs: {"text": text, "ms": 24, "cached": False})
    with TestClient(app) as client:
        yield client


def test_live_upload_shares_asr_and_reports_partial_failures(demo_client, monkeypatch, tmp_path):
    calls = []

    def transcript(file, model, *, keywords, with_logprobs, cache_answers, **kwargs):
        calls.append((model, keywords))
        assert file.read_bytes() == b"audio" and not cache_answers
        if with_logprobs:
            raise TimeoutError()
        return {"text": TEXT, "model": model, "tokens": [], "latency_ms": 42, "cached": False}

    monkeypatch.setattr(systems, "transcribe", transcript)
    meta, events = compare(demo_client, files={"audio": ("call.webm", b"audio", "audio/webm")})
    assert meta["mode"] == "audio"
    assert len(calls) == 3
    assert events["P_C0"]["event"] == "system_error"
    assert events["B2_naive_llm_C3"]["event"] == "system_error"
    assert events["B0_asr_plain"]["event"] == "result"
    main = events[MAIN]["result"]
    assert [a["role"] for a in main["asr"]] == ["input", "second_opinion"]
    assert all(a["latency_ms"] == 42 for a in main["asr"])
    assert not list((tmp_path / "uploads").iterdir())


def test_confirmation_replay_is_scoped_and_uses_original_inputs(demo_client, monkeypatch):
    calls = []

    def transcript(file, model, **kwargs):
        calls.append(model)
        return {"text": TEXT, "model": model, "tokens": [], "latency_ms": 42, "cached": False}

    monkeypatch.setattr(systems, "transcribe", transcript)
    context = {"contacts": [{"name": "Venkatesh"}, {"name": "Venkataraman"}]}
    first, events = compare(demo_client, data={"context": json.dumps(context)},
                            files={"audio": ("call.webm", b"audio", "audio/webm")})
    main = events[MAIN]["result"]
    person = next(e for e in main["entities"] if e["etype"] == "PERSON")
    phone = next(e for e in main["entities"] if e["etype"] == "PHONE")
    assert phone["status"] == person["status"] == "FLAGGED"
    question = next(q for q in main["questions"] if q["entity_id"] == person["id"])
    assert "Venkatesh" in question["choices"]
    assert main["text"][person["start"]:person["end"]] == person["surface"]
    confirm = f"/api/demo/{first['run_id']}/confirm"
    replay = f"/api/demo/{first['run_id']}/replay"
    named = {"system_id": MAIN, "entity_id": person["id"], "canonical": "Venkatesh"}
    with TestClient(app) as other:
        assert other.post(confirm, json=named).status_code == 404
        assert other.post(replay, json={"system_id": MAIN}).status_code == 404
    assert demo_client.post(confirm, json={**named, "entity_id": phone["id"]}).status_code == 400
    assert demo_client.post(confirm, json={**named, "canonical": "Venkatesh 12345"}).status_code == 400
    assert demo_client.post(confirm, json=named).status_code == 200

    before = list(calls)
    result = demo_client.post(replay, json={"system_id": MAIN}).json()
    assert result["text_in"] == main["text_in"] and result["asr"] == main["asr"]
    assert calls == before and result["memory_hits"] == 1 and result["llm_calls"] == 0
    person, phone = result["entities"]
    assert person["source"] == "memory"
    assert result["text"][person["start"]:person["end"]] == "Venkatesh"
    assert result["text"][phone["start"]:phone["end"]] == phone["surface"]
    assert phone["status"] == "FLAGGED"

    monkeypatch.setitem(settings()["demo"], "run_ttl_s", 0)
    assert demo_client.post(replay, json={"system_id": MAIN}).status_code == 404


def test_typed_transcript_and_invalid_form(demo_client):
    first, events = compare(demo_client, data={"text": TEXT})
    assert first["mode"] == "text"
    assert events[MAIN]["result"]["asr"][0]["model"] == "typed"
    assert len(events[MAIN]["result"]["asr"]) == 1
    assert all("scored" not in e["result"] for e in events.values())
    assert demo_client.post("/api/demo/compare", data={"text": "hi", "preset": "test"}).status_code == 400
    bad_context = {"text": "hi", "context": '{"contacts":[1]}'}
    assert demo_client.post("/api/demo/compare", data=bad_context).status_code == 400
    assert demo_client.post("/api/demo/compare", data={"preset": "missing"}).status_code == 404
    assert demo_client.post("/api/demo/compare", files={"audio": ("call.webm", b"")}).status_code == 400


def test_preset_plays_and_scores_without_revealing_non_demo_paths(demo_client, monkeypatch, tmp_path):
    audio = tmp_path / "dev" / "fixture.wav"
    audio.parent.mkdir()
    audio.write_bytes(b"sample")
    monkeypatch.setitem(settings()["paths"], "audio", str(tmp_path))
    catalog = [{"id": "delivery", "label": "Delivery", "voice_source": "Fixture", "audio": str(audio),
                "context": {"places": ["Kondapur"]}, "context_adv": {"places": ["Kondapuru"]},
                "reference": "Callback number 9848012345.", "entities": [{"type": "PHONE", "value": "9848012345"}]}]
    catalog.append({**catalog[0], "id": "private", "audio": str(tmp_path / "private.wav")})
    (tmp_path / "private.wav").write_bytes(b"private")
    file = tmp_path / "catalog.json"
    file.write_text(json.dumps(catalog))
    monkeypatch.setitem(settings()["demo"], "presets", str(file))
    calls = []

    def transcript(file, model, *, keywords, cache_answers, **kwargs):
        calls.append((model, keywords))
        assert cache_answers
        return {"text": TEXT, "model": model, "tokens": [], "latency_ms": 42, "cached": False}

    monkeypatch.setattr(systems, "transcribe", transcript)
    listed = demo_client.get("/api/demo/presets").json()
    assert len(listed) == 1 and "entities" not in listed[0] and "audio" not in listed[0]
    assert demo_client.get(listed[0]["audio_url"]).content == b"sample"
    assert demo_client.get("/api/demo/presets/private/audio").status_code == 404
    first, events = compare(demo_client, data={"preset": "delivery"})
    assert first["preset"] == "delivery"
    assert events["B0_asr_plain"]["result"]["scored"]["silent_errors"] == ["PHONE"]
    assert any(kw and "Kondapuru" in kw for _, kw in calls)


def test_verifier_reports_actual_model_usage_and_replay_skips_it(demo_client, monkeypatch):
    from pehchaan.judge import verifier

    monkeypatch.setitem(settings()["verifier"], "enabled", True)
    calls = []

    def judge(*args, **kwargs):
        calls.append(True)
        return {"choice": "flag", "reason": "Needs clarification"}

    monkeypatch.setattr(verifier, "structured_completion", judge)
    data = {"text": TEXT, "context": json.dumps({"contacts": [{"name": "Venkatesh"}]})}
    first, events = compare(demo_client, data=data)
    main = events[MAIN]["result"]
    assert main["llm_calls"] == 1 and main["verifier_cache_hits"] == 0
    before = len(calls)
    res = demo_client.post(f"/api/demo/{first['run_id']}/replay", json={"system_id": MAIN})
    assert res.status_code == 200 and res.json()["llm_calls"] == res.json()["verifier_cache_hits"] == 0
    assert res.json()["replay_ms"] >= 0 and len(calls) == before


def test_integration_alias_accepts_existing_contract_and_cleans_audio(monkeypatch, tmp_path):
    from app import server

    monkeypatch.setattr(server, "UPLOADS", tmp_path)
    file_paths = []

    def transcription(file, model, **kwargs):
        file_paths.append(file)
        assert file.read_bytes() == b"demo"
        return {"text": "Hello", "model": model, "latency_ms": 10, "tokens": []}

    monkeypatch.setattr(server, "transcribe", transcription)
    with TestClient(app) as client:
        response = client.post("/v1/pehchaan/transcribe", files={"audio": ("demo.wav", b"demo", "audio/wav")})
        assert response.status_code == 200
        assert response.json()["baseline"]["text"] == response.json()["pehchaan"]["text_out"] == "Hello"
        assert len(file_paths) == 2 and not list(tmp_path.iterdir())
