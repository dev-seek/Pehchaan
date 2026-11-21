"""WS /v1/stream: phrases are verified when final, every paid phrase is counted, and limits close the session."""
from __future__ import annotations

import math
from array import array

import pytest
from starlette.websockets import WebSocketDisconnect

from app import access
from app.segmenter import Segmenter
from pehchaan.config import settings
from tests.v1_support import CONTEXT, PASSCODE, TEXT


def collect(ws) -> list[dict]:
    out = []
    while True:
        message = ws.receive_json()
        out.append(message)
        if message["type"] in ("final", "error"):
            return out


def test_stream_needs_a_credential_in_the_first_message(http):
    with http.websocket_connect("/v1/stream") as ws:
        ws.send_json({"type": "start", "mode": "transcript"})
        assert ws.receive_json()["status"] == 401
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == 4401


def test_stream_verifies_external_partials_only_when_final(http):
    with http.websocket_connect("/v1/stream") as ws:
        ws.send_json({"type": "start", "mode": "transcript", "auth": {"passcode": PASSCODE}, "context": CONTEXT})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "transcript", "text": "Main Ravi", "is_final": False})
        ws.send_json({"type": "transcript", "text": TEXT, "is_final": True})
        ws.send_json({"type": "stop"})
        events = collect(ws)
    assert [e["phrase"] for e in events if e["type"] == "phrase"] == [1]
    facts = {e["fact"]["type"]: e["fact"]["status"] for e in events if e["type"] == "fact"}
    assert facts["PHONE"] == "VERIFIED" and facts["PERSON"] in ("VERIFIED", "FIXED")
    assert events[-1]["type"] == "final" and "9848012345" in events[-1]["result"]["verified_text"].replace(" ", "")


def speech(seconds: float) -> bytes:
    return (b"\x00\x20\x00\xe0" * 4000) * int(seconds * 2)


def silence(seconds: float) -> bytes:
    return b"\x00\x00" * int(16000 * seconds)


def test_stream_transcribes_audio_phrase_by_phrase_and_counts_each(http, fake, monkeypatch):
    monkeypatch.setitem(settings()["api"], "per_ip_per_hour", 100)  # calls are counted only when a cap is configured
    with http.websocket_connect("/v1/stream") as ws:
        ws.send_json({"type": "start", "mode": "audio", "auth": {"passcode": PASSCODE}, "context": CONTEXT})
        assert ws.receive_json()["type"] == "ready"
        ws.send_bytes(silence(0.3) + speech(1.5) + silence(1.0) + speech(1.5) + silence(1.0))
        ws.send_json({"type": "stop"})
        events = collect(ws)
    assert len([e for e in events if e["type"] == "phrase"]) == 2 and events[-1]["type"] == "final"
    assert len(access._windows[next(k for k in access._windows if k.startswith("live-hour"))]) == 2


def test_a_stream_is_saved_once_for_its_caller(http, fake):
    context = {**CONTEXT, "user": {"id": "caller-live", "city": "Hyderabad"}}
    with http.websocket_connect("/v1/stream") as ws:
        ws.send_json({"type": "start", "mode": "audio", "auth": {"passcode": PASSCODE}, "context": context})
        ws.receive_json()
        ws.send_bytes(silence(0.3) + speech(1.5) + silence(1.0) + speech(1.5) + silence(1.0))
        ws.send_json({"type": "stop"})
        final = collect(ws)[-1]
    calls = http.get("/v1/calls", params={"caller": "caller-live"}, headers={"X-Demo-Passcode": PASSCODE}).json()["calls"]
    assert [c["id"] for c in calls] == [final["result"]["call_id"]] and calls[0]["source"] == "stream"


def test_stream_stops_at_the_audio_limit(http, monkeypatch):
    monkeypatch.setitem(settings()["api"]["stream"], "max_audio_seconds", 1)
    with http.websocket_connect("/v1/stream") as ws:
        ws.send_json({"type": "start", "mode": "audio", "auth": {"passcode": PASSCODE}})
        ws.receive_json()
        ws.send_bytes(silence(1.2))
        assert ws.receive_json()["status"] == 413


def test_segmenter_ignores_pure_silence():
    cfg = settings()["api"]["stream"]
    cut = Segmenter(
        16000,
        pause_ms=cfg["pause_ms"],
        min_s=cfg["min_phrase_s"],
        max_s=cfg["max_phrase_s"],
        min_level=cfg["min_level"],
        over_floor=cfg["over_floor"],
    )
    assert cut.feed(silence(5)) == [] and cut.flush() is None


def test_segmenter_forces_a_cut_on_nonstop_speech():
    cut = Segmenter(16000, pause_ms=600, min_s=1, max_s=2, min_level=180, over_floor=2.5)
    assert len(cut.feed(silence(0.3) + speech(5))) == 2


def test_segmenter_ends_a_phrase_at_a_natural_pause():
    cfg = settings()["api"]["stream"]
    rate = cfg["sample_rate"]
    speech = array("h", (int(3000 * math.sin(i * 0.2)) for i in range(int(1.5 * rate)))).tobytes()
    pause = b"\x00\x00" * int(0.45 * rate)
    cut = Segmenter(
        rate,
        pause_ms=cfg["pause_ms"],
        min_s=cfg["min_phrase_s"],
        max_s=cfg["max_phrase_s"],
        min_level=cfg["min_level"],
        over_floor=cfg["over_floor"],
    )
    phrases = cut.feed(b"\x00\x00" * int(0.3 * rate) + speech + pause + speech + pause)
    assert len(phrases) == 2
